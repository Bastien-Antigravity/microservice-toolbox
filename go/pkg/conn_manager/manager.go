package conn_manager

import (
	"fmt"
	"io"
	"math"
	"math/rand"
	"strings"
	"time"

	safesocket "github.com/Bastien-Antigravity/safe-socket"
)

// OnErrorHandler is a callback for reporting errors to the consumer of the toolbox.
type OnErrorHandler func(name string, source string, err error, originalMsg string)

// -----------------------------------------------------------------------------
// NetworkManager handles reliable connection establishment with retries.
type NetworkManager struct {
	MaxRetries     int // Supports -1 for infinite retries
	BaseDelay      time.Duration
	MaxDelay       time.Duration
	ConnectTimeout time.Duration
	Backoff        float64
	Jitter         float64 // 0.0 to 1.0 (multiplier for delay added as randomness)

	// OnError is an optional hook for custom error reporting (e.g. to a logger or alert system).
	OnError OnErrorHandler
}

// -----------------------------------------------------------------------------
// NewNetworkManager creates a manager with provided retry policies (durations in milliseconds).
func NewNetworkManager(maxRetries int, baseDelayMs, maxDelayMs, connectTimeoutMs int, backoff, jitter float64) *NetworkManager {
	return &NetworkManager{
		MaxRetries:     maxRetries,
		BaseDelay:      time.Duration(baseDelayMs) * time.Millisecond,
		MaxDelay:       time.Duration(maxDelayMs) * time.Millisecond,
		ConnectTimeout: time.Duration(connectTimeoutMs) * time.Millisecond,
		Backoff:        backoff,
		Jitter:         jitter,
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

		fmt.Printf("ManagedConnection: Initial connection to %s failed: %v. Retrying in %v...\n", address, err, time.Duration(delay))
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
			nm.OnError("NetworkManager", "ConnectBlocking", err, fmt.Sprintf("Failed to connect to %s:%s", *ip, *port))
		}
	}
	return mc
}
