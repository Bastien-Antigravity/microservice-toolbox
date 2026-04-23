package conn_manager

import (
	"fmt"
	"io"
	"math"
	"math/rand"
	"strings"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/utils"
	safesocket "github.com/Bastien-Antigravity/safe-socket"
)

// OnErrorHandler is a callback triggered on every connection attempt failure.
// attempt: current failure count (starting at 1 for first error).
// err: the specific error that triggered the failure.
// source: the component where the error occurred (e.g. "ManagedConnection.reconnect").
// msg: a descriptive message providing additional context.
type OnErrorHandler func(attempt int, err error, source string, msg string)
 
// ConnectionMode defines how the manager handles the initial connection.
type ConnectionMode int
 
const (
	// ModeBlocking blocks until connection is successful (or MaxRetries reached).
	ModeBlocking ConnectionMode = iota
	// ModeNonBlocking returns immediately and retries in the background.
	ModeNonBlocking
	// ModeIndefinite blocks indefinitely until connection is successful.
	ModeIndefinite
)

// -----------------------------------------------------------------------------
// NetworkManager handles reliable connection establishment with retries.
type NetworkManager struct {
	MaxRetries     int // Supports -1 for infinite retries
	BaseDelay      time.Duration
	MaxDelay       time.Duration
	ConnectTimeout time.Duration
	Backoff        float64
	Jitter         float64 // 0.0 to 1.0 (multiplier for delay added as randomness)

	// OnError is an optional hook for fine-grained error reporting and retry logic 
	// (e.g., execute after X errors, or on specific error types).
	OnError OnErrorHandler
	// Logger is the logger to use for logging.
	Logger  utils.Logger
}

// -----------------------------------------------------------------------------
// NewNetworkManager creates a manager with provided retry policies (durations in milliseconds).
func NewNetworkManager(maxRetries int, baseDelayMs, maxDelayMs, connectTimeoutMs int, backoff, jitter float64) *NetworkManager {
	return NewNetworkManagerWithLogger(maxRetries, baseDelayMs, maxDelayMs, connectTimeoutMs, backoff, jitter, nil)
}

// NewNetworkManagerWithLogger creates a manager with provided retry policies and an explicit logger.
func NewNetworkManagerWithLogger(maxRetries int, baseDelayMs, maxDelayMs, connectTimeoutMs int, backoff, jitter float64, logger utils.Logger) *NetworkManager {
	return &NetworkManager{
		MaxRetries:     maxRetries,
		BaseDelay:      time.Duration(baseDelayMs) * time.Millisecond,
		MaxDelay:       time.Duration(maxDelayMs) * time.Millisecond,
		ConnectTimeout: time.Duration(connectTimeoutMs) * time.Millisecond,
		Backoff:        backoff,
		Jitter:         jitter,
		Logger:         utils.EnsureSafeLogger(logger),
	}
}

// -----------------------------------------------------------------------------
// EstablishConnection attempts a single connection to the resolved address.
func (nm *NetworkManager) EstablishConnection(ip, port, publicIP *string, profile string) (io.WriteCloser, error) {
	cleanIP := strings.Trim(*ip, "\"")
	cleanPort := strings.Trim(*port, "\"")
	address := fmt.Sprintf("%s:%s", cleanIP, cleanPort)
	return safesocket.Create(profile, address, *publicIP, "client", true)
}

// -----------------------------------------------------------------------------
// ConnectWithRetry attempts to connect and returns a ManagedConnection.
func (nm *NetworkManager) ConnectWithRetry(ip, port, publicIP *string, profile string) (io.WriteCloser, error) {
	mc := &ManagedConnection{
		ip:       ip,
		port:     port,
		publicIP: publicIP,
		profile:  profile,
		nm:       nm,
	}

	// Try initial connection
	cleanIP := strings.Trim(*ip, "\"")
	cleanPort := strings.Trim(*port, "\"")
	address := fmt.Sprintf("%s:%s", cleanIP, cleanPort)
	var lastErr error
	for i := 0; (nm.MaxRetries == -1) || (i < nm.MaxRetries); i++ {
		conn, err := nm.EstablishConnection(ip, port, publicIP, profile)
		if err == nil {
			mc.currentConn = conn
			return mc, nil
		}
		lastErr = err

		// Calculate backoff
		delay := float64(nm.BaseDelay) * math.Pow(nm.Backoff, float64(i))
		if delay > float64(nm.MaxDelay) {
			delay = float64(nm.MaxDelay)
		}

		// Apply jitter
		if nm.Jitter > 0 {
			jitterVal := rand.Float64() * nm.Jitter * delay
			delay += jitterVal
		}

		nm.Logger.Warning("ManagedConnection: Initial connection to %s failed: %v. Retrying in %v...", address, err, time.Duration(delay))
		if nm.OnError != nil {
			nm.OnError(i+1, err, "NetworkManager", fmt.Sprintf("Initial connection failure to %s", address))
		}
		time.Sleep(time.Duration(delay))
		address = fmt.Sprintf("%s:%s", cleanIP, cleanPort)
	}

	return nil, fmt.Errorf("%w: %s after %d attempts (last error: %v)", ErrMaxRetriesReached, address, nm.MaxRetries, lastErr)
}

// -----------------------------------------------------------------------------
// ConnectBlocking indefinitely retries connection until successful and returns ManagedConnection.
func (nm *NetworkManager) ConnectBlocking(ip, port, publicIP *string, profile string) io.WriteCloser {
	mc := &ManagedConnection{
		ip:       ip,
		port:     port,
		publicIP: publicIP,
		profile:  profile,
		nm:       nm,
	}

	// Use internal reconnect logic to establish initial connection
	if err := mc.reconnect(); err != nil {
		if nm.OnError != nil {
			nm.OnError(1, err, "NetworkManager", fmt.Sprintf("Failed to connect to %s:%s", *ip, *port))
		}
	}
	return mc
}

// ConnectNonBlocking immediately returns a ManagedConnection and attempts to connect in the background.
func (nm *NetworkManager) ConnectNonBlocking(ip, port, publicIP *string, profile string) io.WriteCloser {
	mc := &ManagedConnection{
		ip:       ip,
		port:     port,
		publicIP: publicIP,
		profile:  profile,
		nm:       nm,
	}

	// Start reconnection loop in background
	go func() {
		if err := mc.reconnect(); err != nil {
			if nm.OnError != nil {
				nm.OnError(1, err, "NetworkManager", fmt.Sprintf("Failed to connect to %s:%s in background", *ip, *port))
			}
		}
	}()

	return mc
}
// Connect establishes a connection using the specified mode.
func (nm *NetworkManager) Connect(ip, port, publicIP *string, profile string, mode ConnectionMode) io.WriteCloser {
	switch mode {
	case ModeBlocking:
		mc, err := nm.ConnectWithRetry(ip, port, publicIP, profile)
		if err != nil {
			// Return a ManagedConnection that can be used later (reconnect on Write)
			return &ManagedConnection{
				ip:       ip,
				port:     port,
				publicIP: publicIP,
				profile:  profile,
				nm:       nm,
			}
		}
		return mc
	case ModeNonBlocking:
		return nm.ConnectNonBlocking(ip, port, publicIP, profile)
	case ModeIndefinite:
		return nm.ConnectBlocking(ip, port, publicIP, profile)
	default:
		return nm.ConnectBlocking(ip, port, publicIP, profile)
	}
}

// -----------------------------------------------------------------------------
// Strategies

// NewCriticalStrategy creates a manager configured for critical services: 
// Infinite retries, aggressive backoff.
func NewCriticalStrategy(logger utils.Logger) *NetworkManager {
	return NewNetworkManagerWithLogger(-1, 200, 10000, 5000, 2.0, 0.2, logger)
}

// NewStandardStrategy creates a manager for standard services:
// Limited retries, moderate backoff.
func NewStandardStrategy(logger utils.Logger) *NetworkManager {
	return NewNetworkManagerWithLogger(10, 500, 30000, 5000, 1.5, 0.1, logger)
}

// NewPerformanceStrategy creates a manager for high-performance services:
// Short timeouts, low delay, background reconnection.
func NewPerformanceStrategy(logger utils.Logger) *NetworkManager {
	return NewNetworkManagerWithLogger(-1, 100, 2000, 1000, 1.2, 0.0, logger)
}
