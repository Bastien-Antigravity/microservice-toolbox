package conn_manager

import (
	"fmt"
	"io"
	"sync"
	"time"
)

// -----------------------------------------------------------------------------
// ManagedConnection wraps a connection and handles automatic reconnection.
type ManagedConnection struct {
	ip          *string
	port        *string
	publicIP    *string
	profile     string
	nm          *NetworkManager
	currentConn io.WriteCloser
	mu          sync.Mutex
}

// -----------------------------------------------------------------------------

func (mc *ManagedConnection) Write(p []byte) (n int, err error) {
	mc.mu.Lock()
	defer mc.mu.Unlock()

	// If no connection, try to reconnect immediately (blocking)
	if mc.currentConn == nil {
		if err := mc.reconnect(); err != nil {
			return 0, err
		}
	}

	n, err = mc.currentConn.Write(p)
	if err != nil {
		mc.nm.Logger.Warning("ManagedConnection: Write failed (%v). Reconnecting...", err)
		mc.currentConn.Close()
		mc.currentConn = nil

		// Reconnect and retry once
		if rErr := mc.reconnect(); rErr != nil {
			return 0, fmt.Errorf("%w: base write error: %v; reconnect error: %v", ErrWriteFailed, err, rErr)
		}
		return mc.currentConn.Write(p) // Retry
	}
	return n, nil
}

// -----------------------------------------------------------------------------

func (mc *ManagedConnection) Close() error {
	mc.mu.Lock()
	defer mc.mu.Unlock()
	if mc.currentConn != nil {
		return mc.currentConn.Close()
	}
	return nil
}

// -----------------------------------------------------------------------------

func (mc *ManagedConnection) reconnect() error {
	var address string
	delay := mc.nm.BaseDelay

	for {
		conn, err := mc.nm.EstablishConnection(mc.ip, mc.port, mc.publicIP, mc.profile)
		if err == nil {
			address = fmt.Sprintf("%s:%s", *mc.ip, *mc.port)
			mc.nm.Logger.Info("ManagedConnection: Reconnected to %s", address)
			mc.currentConn = conn
			return nil
		}

		// Report failure to the optional OnError hook
		if mc.nm.OnError != nil {
			mc.nm.OnError("NetworkManager", "ManagedConnection.reconnect", err, fmt.Sprintf("Failed to recover connection to %s:%s", *mc.ip, *mc.port))
		}

		time.Sleep(delay)
		delay *= 2
		if delay > mc.nm.MaxDelay {
			delay = mc.nm.MaxDelay
		}
	}
}
