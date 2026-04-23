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
	ip           *string
	port         *string
	publicIP     *string
	profile      string
	nm           *NetworkManager
	currentConn  io.WriteCloser
	reconnecting bool
	mu           sync.Mutex
}

// -----------------------------------------------------------------------------

func (mc *ManagedConnection) Write(p []byte) (n int, err error) {
	mc.mu.Lock()
	defer mc.mu.Unlock()

	// If no connection, try to reconnect immediately (blocking)
	if mc.currentConn == nil {
		mc.mu.Unlock()
		if err := mc.reconnect(); err != nil {
			mc.mu.Lock()
			return 0, err
		}
		mc.mu.Lock()
	}

	n, err = mc.currentConn.Write(p)
	if err != nil {
		mc.nm.Logger.Warning("ManagedConnection: Write failed (%v). Reconnecting...", err)
		mc.currentConn.Close()
		mc.currentConn = nil

		// Reconnect and retry once (unlocking during reconnect)
		mc.mu.Unlock()
		if rErr := mc.reconnect(); rErr != nil {
			mc.mu.Lock()
			return 0, fmt.Errorf("%w: base write error: %v; reconnect error: %v", ErrWriteFailed, err, rErr)
		}
		mc.mu.Lock()

		if mc.currentConn == nil {
			return 0, fmt.Errorf("%w: reconnection succeeded but currentConn is still nil", ErrWriteFailed)
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
	mc.mu.Lock()
	if mc.reconnecting {
		// Already reconnecting. Wait for it or just block until it's done.
		// For simplicity, we'll wait for the currentConn to become non-nil
		// by checking in a loop or using a condition variable.
		// Given the "easiest way" instruction, let's just let the caller loop a bit
		// or block on the mutex after releasing it.

		// Actually, better: if already reconnecting, we should block until it's done.
		mc.mu.Unlock()
		for {
			mc.mu.Lock()
			if mc.currentConn != nil {
				mc.mu.Unlock()
				return nil
			}
			if !mc.reconnecting {
				// Reconnection failed or was canceled?
				// Should we try again?
				mc.reconnecting = true
				mc.mu.Unlock()
				break
			}
			mc.mu.Unlock()
			time.Sleep(100 * time.Millisecond)
		}
	} else {
		mc.reconnecting = true
		mc.mu.Unlock()
	}

	// Actual reconnection loop
	var address string
	delay := mc.nm.BaseDelay
	i := 0

	for {
		conn, err := mc.nm.EstablishConnection(mc.ip, mc.port, mc.publicIP, mc.profile)
		if err == nil {
			mc.mu.Lock()
			address = fmt.Sprintf("%s:%s", *mc.ip, *mc.port)
			mc.nm.Logger.Info("ManagedConnection: Reconnected to %s", address)
			mc.currentConn = conn
			mc.reconnecting = false
			mc.mu.Unlock()
			return nil
		}

		// Report failure to the optional hook
		if mc.nm.OnError != nil {
			mc.nm.OnError(i+1, err, "NetworkManager", fmt.Sprintf("Failed to recover connection to %s:%s", *mc.ip, *mc.port))
		}

		time.Sleep(delay)
		delay *= 2
		i++
		if delay > mc.nm.MaxDelay {
			delay = mc.nm.MaxDelay
		}
	}
}
