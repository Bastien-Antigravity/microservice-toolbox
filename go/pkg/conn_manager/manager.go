package conn_manager

import (
	"fmt"
	"io"
	"math"
	"strings"
	"time"

	safesocket "github.com/Bastien-Antigravity/safe-socket"
)

// OnErrorHandler is a callback for reporting errors to the consumer of the toolbox.
type OnErrorHandler func(name string, source string, err error, originalMsg string)

// -----------------------------------------------------------------------------
// NetworkManager handles reliable connection establishment with retries.
type NetworkManager struct {
	MaxRetries     int
	BaseDelay      time.Duration
	MaxDelay       time.Duration
	ConnectTimeout time.Duration

	// OnError is an optional hook for custom error reporting (e.g. to a logger or alert system).
	OnError OnErrorHandler
}

// -----------------------------------------------------------------------------
// NewNetworkManager creates a manager with default retry policies.
func NewNetworkManager() *NetworkManager {
	return &NetworkManager{
		MaxRetries:     5,
		BaseDelay:      200 * time.Millisecond,
		MaxDelay:       5 * time.Second,
		ConnectTimeout: 2 * time.Second,
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
	var err error
	for i := 0; i < nm.MaxRetries; i++ {
		conn, err = nm.EstablishConnection(ip, port, publicIP, profile)
		if err == nil {
			mc.currentConn = conn
			return mc, nil
		}

		delay := float64(nm.BaseDelay) * math.Pow(2, float64(i))
		if delay > float64(nm.MaxDelay) {
			delay = float64(nm.MaxDelay)
		}
		fmt.Printf("ManagedConnection: Initial connection to %s failed: %v. Retrying in %v...\n", address, err, time.Duration(delay))
		time.Sleep(time.Duration(delay))
		address = fmt.Sprintf("%s:%s", *ip, *port)
	}

	return nil, fmt.Errorf("%w: %s after %d attempts (last error: %v)", ErrMaxRetriesReached, address, nm.MaxRetries, err)
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
