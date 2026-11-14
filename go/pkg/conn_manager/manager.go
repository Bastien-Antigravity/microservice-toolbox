// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Manages polyglot inter-service network connections with lifecycle hooks and circuit breakers.
//
// DATA FLOW:
// Service Request -> Connection Pool / ManagedConnection -> Active Inter-service Link
//
// KEY PARAMETERS:
// - connections: Active managed connections map.
// - strategies: Backoff and retry presets.
// -----------------------------------------------------------------------------

package conn_manager

import (
	"fmt"
	"io"
	"math"
	"math/rand"
	"net"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
	safesocket "github.com/Bastien-Antigravity/safe-socket"
)

// OnErrorHandler is a callback triggered on every connection attempt failure.
// attempt: current failure count (starting at 1 for first error).
// err: the specific error that triggered the failure.
// source: the component where the error occurred (e.g. "ManagedConnection.reconnect").
// msg: a descriptive message providing additional context.
type OnErrorHandler func(attempt int, err error, source string, msg string)

// ReloadHandler is a callback triggered on error after 3 consecutive failed connection attempts (and every 3 attempts thereafter).
// attempt: current failure count (e.g. 3, 6, 9...).
// Returns updated (newIP, newPort) from configuration reload and any error encountered.
type ReloadHandler func(attempt int) (newIP, newPort string, err error)

// ConnectionMode defines how the manager handles the initial connection behavior.
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
	// MaxRetries is the maximum number of connection attempts. Set to -1 for infinite retries.
	MaxRetries int
	// BaseDelay is the starting delay between retry attempts.
	BaseDelay time.Duration
	// MaxDelay is the upper limit for the backoff delay.
	MaxDelay time.Duration
	// ConnectTimeout is the timeout for each individual connection attempt.
	ConnectTimeout time.Duration
	// Backoff is the multiplier for the delay after each failed attempt.
	Backoff float64
	// Jitter is the amount of randomness (0.0 to 1.0) added to the delay.
	Jitter float64

	// OnError is an optional hook for fine-grained error reporting and retry logic.
	OnError OnErrorHandler
	// OnReloadConfig is an optional hook invoked after 3 consecutive failed attempts to reload destination coordinates.
	OnReloadConfig ReloadHandler
	// Logger is the logger instance used for reporting status and errors.
	Logger logger.Logger
	// AppConfig is an optional pointer to the ecosystem AppConfig for automatic capability resolution and self-healing.
	AppConfig *config.AppConfig
	// Dialer is an optional connection factory override (e.g. for testing with net.Pipe or mock transports).
	Dialer func(ep *Endpoint) (io.WriteCloser, error)
}

// -----------------------------------------------------------------------------
// NewNetworkManager creates a resilient NetworkManager combining AppConfig and Logger pointers.
// Passing ac binds AppConfig for automated capability resolution and self-healing.
// If l is nil and ac is provided, ac.Logger is automatically inherited.
func NewNetworkManager(ac *config.AppConfig, l logger.Logger) *NetworkManager {
	if l == nil && ac != nil {
		l = ac.Logger
	}
	return &NetworkManager{
		MaxRetries:     -1,
		BaseDelay:      200 * time.Millisecond,
		MaxDelay:       5 * time.Second,
		ConnectTimeout: 2 * time.Second,
		Backoff:        2.0,
		Jitter:         0.0,
		Logger:         logger.EnsureSafeLogger(l),
		AppConfig:      ac,
	}
}

// WithPolicy configures custom retry policy parameters on NetworkManager.
func (nm *NetworkManager) WithPolicy(maxRetries int, baseDelayMs, maxDelayMs, connectTimeoutMs int, backoff, jitter float64) *NetworkManager {
	nm.MaxRetries = maxRetries
	nm.BaseDelay = time.Duration(baseDelayMs) * time.Millisecond
	nm.MaxDelay = time.Duration(maxDelayMs) * time.Millisecond
	nm.ConnectTimeout = time.Duration(connectTimeoutMs) * time.Millisecond
	nm.Backoff = backoff
	nm.Jitter = jitter
	return nm
}

// NewNetworkManagerWithPolicy creates a manager with explicit retry policies (durations in milliseconds).
func NewNetworkManagerWithPolicy(maxRetries int, baseDelayMs, maxDelayMs, connectTimeoutMs int, backoff, jitter float64) *NetworkManager {
	return NewNetworkManager(nil, nil).WithPolicy(maxRetries, baseDelayMs, maxDelayMs, connectTimeoutMs, backoff, jitter)
}

// NewNetworkManagerWithConfig creates a resilient NetworkManager pre-bound to the ecosystem AppConfig.
func NewNetworkManagerWithConfig(ac *config.AppConfig) *NetworkManager {
	return NewNetworkManager(ac, nil)
}

// NewNetworkManagerWithLogger creates a manager with provided retry policies and an explicit logger.
func NewNetworkManagerWithLogger(maxRetries int, baseDelayMs, maxDelayMs, connectTimeoutMs int, backoff, jitter float64, l logger.Logger) *NetworkManager {
	return NewNetworkManager(nil, l).WithPolicy(maxRetries, baseDelayMs, maxDelayMs, connectTimeoutMs, backoff, jitter)
}

// -----------------------------------------------------------------------------
// GetNextDelay calculates the delay for the next attempt using backoff and jitter.
// attempt is 0-indexed.
func (nm *NetworkManager) GetNextDelay(attempt int) time.Duration {
	delay := float64(nm.BaseDelay) * math.Pow(nm.Backoff, float64(attempt))
	if delay > float64(nm.MaxDelay) {
		delay = float64(nm.MaxDelay)
	}

	if nm.Jitter > 0 {
		jitterVal := rand.Float64() * nm.Jitter * delay
		delay += jitterVal
	}

	return time.Duration(delay)
}

// -----------------------------------------------------------------------------
// EstablishConnection attempts a single connection using the immutable Endpoint pointer.
// Zero temporary variables, zero defensive nil-checks, and zero string formatting overhead.
func (nm *NetworkManager) EstablishConnection(ep *Endpoint) (io.WriteCloser, error) {
	if nm.Dialer != nil {
		return nm.Dialer(ep)
	}
	return safesocket.Create(ep.Profile, ep.Address, ep.PublicIP, "client", true)
}

// EstablishConnectionRaw attempts a single connection from string pointers (backwards compatibility).
func (nm *NetworkManager) EstablishConnectionRaw(ip, port, publicIP *string, profile string) (io.WriteCloser, error) {
	var sIP, sPort, sPub string
	if ip != nil {
		sIP = *ip
	}
	if port != nil {
		sPort = *port
	}
	if publicIP != nil {
		sPub = *publicIP
	}
	return nm.EstablishConnection(NewEndpoint(sIP, sPort, sPub, profile))
}

// -----------------------------------------------------------------------------
// ConnectWithRetryEndpoint attempts to connect using an immutable Endpoint pointer.
func (nm *NetworkManager) ConnectWithRetryEndpoint(ep *Endpoint) (*ManagedConnection, error) {
	mc := NewManagedConnection(nm, ep)

	var lastErr error
	for i := 0; (nm.MaxRetries == -1) || (i < nm.MaxRetries); i++ {
		attempt := i + 1
		if attempt%3 == 0 {
			mc.triggerReload(attempt)
		}

		currentEP := mc.endpoint.Load()
		conn, err := nm.EstablishConnection(currentEP)
		if err == nil {
			mc.currentConn.Store(&conn)
			return mc, nil
		}
		lastErr = err

		delay := nm.GetNextDelay(i)
		nm.Logger.Warning("ManagedConnection: Initial connection to %s failed: %v. Retrying in %v...", currentEP.Address, err, delay)
		if nm.OnError != nil {
			nm.OnError(attempt, err, "NetworkManager", fmt.Sprintf("Initial connection failure to %s", currentEP.Address))
		}

		select {
		case <-mc.closing:
			return nil, io.ErrClosedPipe
		case <-time.After(delay):
		}
	}

	currentEP := mc.endpoint.Load()
	return nil, fmt.Errorf("NetworkManager: failed to connect to %s after %d attempts (last error: %w)", currentEP.Address, nm.MaxRetries, lastErr)
}

// ConnectWithRetry attempts to connect and returns a ManagedConnection wrapper.
func (nm *NetworkManager) ConnectWithRetry(ip, port, publicIP *string, profile string) (io.WriteCloser, error) {
	var sIP, sPort, sPub string
	if ip != nil {
		sIP = *ip
	}
	if port != nil {
		sPort = *port
	}
	if publicIP != nil {
		sPub = *publicIP
	}
	return nm.ConnectWithRetryEndpoint(NewEndpoint(sIP, sPort, sPub, profile))
}

// -----------------------------------------------------------------------------
// ConnectBlockingEndpoint indefinitely retries connection until successful and returns ManagedConnection.
func (nm *NetworkManager) ConnectBlockingEndpoint(ep *Endpoint) *ManagedConnection {
	mc := NewManagedConnection(nm, ep)
	if err := mc.reconnect(); err != nil {
		if nm.OnError != nil {
			nm.OnError(1, err, "NetworkManager", fmt.Sprintf("Failed to connect to %s", ep.Address))
		}
	}
	return mc
}

// ConnectBlocking indefinitely retries connection from raw parameters (backwards compatibility).
func (nm *NetworkManager) ConnectBlocking(ip, port, publicIP *string, profile string) *ManagedConnection {
	var sIP, sPort, sPub string
	if ip != nil {
		sIP = *ip
	}
	if port != nil {
		sPort = *port
	}
	if publicIP != nil {
		sPub = *publicIP
	}
	return nm.ConnectBlockingEndpoint(NewEndpoint(sIP, sPort, sPub, profile))
}

// ConnectNonBlockingEndpoint immediately returns a ManagedConnection and attempts to connect in background.
func (nm *NetworkManager) ConnectNonBlockingEndpoint(ep *Endpoint) *ManagedConnection {
	mc := NewManagedConnection(nm, ep)
	go func() {
		if err := mc.reconnect(); err != nil {
			if nm.OnError != nil {
				nm.OnError(1, err, "NetworkManager", fmt.Sprintf("Failed to connect to %s in background", ep.Address))
			}
		}
	}()
	return mc
}

// ConnectNonBlocking immediately returns a ManagedConnection and attempts to connect in background (backwards compatibility).
func (nm *NetworkManager) ConnectNonBlocking(ip, port, publicIP *string, profile string) *ManagedConnection {
	var sIP, sPort, sPub string
	if ip != nil {
		sIP = *ip
	}
	if port != nil {
		sPort = *port
	}
	if publicIP != nil {
		sPub = *publicIP
	}
	return nm.ConnectNonBlockingEndpoint(NewEndpoint(sIP, sPort, sPub, profile))
}

// ConnectEndpoint establishes a connection using the specified mode with an immutable Endpoint pointer.
func (nm *NetworkManager) ConnectEndpoint(ep *Endpoint, mode ConnectionMode) *ManagedConnection {
	switch mode {
	case ModeBlocking:
		mc, err := nm.ConnectWithRetryEndpoint(ep)
		if err != nil {
			return NewManagedConnection(nm, ep)
		}
		return mc
	case ModeNonBlocking:
		return nm.ConnectNonBlockingEndpoint(ep)
	case ModeIndefinite:
		return nm.ConnectBlockingEndpoint(ep)
	default:
		return nm.ConnectBlockingEndpoint(ep)
	}
}

// Connect establishes a connection using raw parameters (backwards compatibility).
func (nm *NetworkManager) Connect(ip, port, publicIP *string, profile string, mode ConnectionMode) *ManagedConnection {
	var sIP, sPort, sPub string
	if ip != nil {
		sIP = *ip
	}
	if port != nil {
		sPort = *port
	}
	if publicIP != nil {
		sPub = *publicIP
	}
	return nm.ConnectEndpoint(NewEndpoint(sIP, sPort, sPub, profile), mode)
}

// -----------------------------------------------------------------------------
// ConnectCapability resolves the target capability from AppConfig, creates an immutable Endpoint pointer,
// and establishes a lock-free ManagedConnection bound to AppConfig. On 3 failed attempts, it automatically syncs AppConfig.
func (nm *NetworkManager) ConnectCapability(capability string, mode ConnectionMode) (*ManagedConnection, error) {
	if nm.AppConfig == nil {
		return nil, fmt.Errorf("NetworkManager: AppConfig is nil, cannot resolve capability %s", capability)
	}
	addr, err := nm.AppConfig.GetListenAddr(capability)
	if err != nil {
		return nil, fmt.Errorf("NetworkManager: failed to resolve capability %s: %w", capability, err)
	}
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		return nil, fmt.Errorf("NetworkManager: invalid address %q for capability %s: %w", addr, capability, err)
	}
	publicIP := ""
	if nm.AppConfig.Config != nil {
		publicIP = nm.AppConfig.Config.Common.PublicIP
	}

	profile := "auto"
	if nm.AppConfig.Config != nil && nm.AppConfig.Config.Capabilities != nil {
		if capMap, ok := nm.AppConfig.Config.Capabilities[capability].(map[string]interface{}); ok {
			if p, ok := capMap["profile"].(string); ok && p != "" {
				profile = p
			}
		}
	} else if nm.AppConfig.Profile != "" && nm.AppConfig.Profile != "standalone" && nm.AppConfig.Profile != "test" && nm.AppConfig.Profile != "staging" && nm.AppConfig.Profile != "production" {
		profile = nm.AppConfig.Profile
	}
	ep := NewEndpoint(host, port, publicIP, profile)
	mc := NewManagedConnection(nm, ep)
	mc.capability = capability

	switch mode {
	case ModeNonBlocking:
		go func() {
			_ = mc.reconnect()
		}()
		return mc, nil
	default:
		if err := mc.reconnect(); err != nil {
			return nil, err
		}
		return mc, nil
	}
}

// -----------------------------------------------------------------------------
// Strategies

// NewCriticalStrategy creates a manager configured for critical services with infinite retries.
func NewCriticalStrategy(l logger.Logger) *NetworkManager {
	return NewNetworkManager(nil, l).WithPolicy(-1, 200, 10000, 5000, 2.0, 0.2)
}

// NewStandardStrategy creates a manager for standard services with limited retries.
func NewStandardStrategy(l logger.Logger) *NetworkManager {
	return NewNetworkManager(nil, l).WithPolicy(10, 500, 30000, 5000, 1.5, 0.1)
}

// NewPerformanceStrategy creates a manager for high-performance services with background reconnection.
func NewPerformanceStrategy(l logger.Logger) *NetworkManager {
	return NewNetworkManager(nil, l).WithPolicy(-1, 100, 2000, 1000, 1.2, 0.0)
}
