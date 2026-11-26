// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Represents a resilient, auto-reconnecting network connection with exponential backoff.
//
// DATA FLOW:
// Network Events -> Reconnect Loop + Backoff -> Active Socket Connection
//
// KEY PARAMETERS:
// - target: Network endpoint address.
// - backoff: Reconnection retry delay with randomized jitter.
// -----------------------------------------------------------------------------

package conn_manager

import (
	"fmt"
	"io"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
)

// -----------------------------------------------------------------------------
// Endpoint holds immutable destination coordinates for a connection.
// Precalculates Address on the cold path to eliminate hot-path formatting and parsing.
type Endpoint struct {
	IP       string
	Port     string
	PublicIP string
	Profile  string
	Address  string // pre-formatted "IP:Port"
}

// NewEndpoint builds an immutable Endpoint on the cold path.
func NewEndpoint(ip, port, publicIP, profile string) *Endpoint {
	return &Endpoint{
		IP:       ip,
		Port:     port,
		PublicIP: publicIP,
		Profile:  profile,
		Address:  ip + ":" + port,
	}
}

// -----------------------------------------------------------------------------
// ManagedConnection wraps a connection and handles automatic reconnection lock-free.
type ManagedConnection struct {
	endpoint    atomic.Pointer[Endpoint]
	currentConn atomic.Pointer[io.WriteCloser]
	nm          *NetworkManager
	appConfig   *config.AppConfig
	capability  string
	reconnectMu sync.Mutex
	closeOnce   sync.Once
	closing     chan struct{}
}

// NewManagedConnection creates a new connection wrapper with an immutable Endpoint pointer.
func NewManagedConnection(nm *NetworkManager, ep *Endpoint) *ManagedConnection {
	mc := &ManagedConnection{
		nm:      nm,
		closing: make(chan struct{}),
	}
	if ep != nil {
		mc.endpoint.Store(ep)
	}
	if nm != nil {
		mc.appConfig = nm.AppConfig
	}
	return mc
}

// NewManagedConnectionRaw creates a ManagedConnection from string pointers (backwards compatibility).
func NewManagedConnectionRaw(nm *NetworkManager, ip, port, publicIP *string, profile string) *ManagedConnection {
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
	return NewManagedConnection(nm, NewEndpoint(sIP, sPort, sPub, profile))
}

// UpdateEndpoint atomically updates the target destination IP and Port.
func (mc *ManagedConnection) UpdateEndpoint(newIP, newPort string) {
	old := mc.endpoint.Load()
	pubIP := ""
	profile := ""
	if old != nil {
		pubIP = old.PublicIP
		profile = old.Profile
	}
	mc.endpoint.Store(NewEndpoint(newIP, newPort, pubIP, profile))
}

// GetEndpoint returns the current IP and Port destination coordinates lock-free.
func (mc *ManagedConnection) GetEndpoint() (string, string) {
	ep := mc.endpoint.Load()
	if ep == nil {
		return "", ""
	}
	return ep.IP, ep.Port
}

// Endpoint returns the current immutable Endpoint pointer.
func (mc *ManagedConnection) Endpoint() *Endpoint {
	return mc.endpoint.Load()
}

// currentEndpoint returns the active Endpoint, refreshing from AppConfig's atomic LiveConfig if bound to a capability.
func (mc *ManagedConnection) currentEndpoint() *Endpoint {
	ep := mc.endpoint.Load()
	if mc.appConfig != nil && mc.capability != "" {
		if newAddr, err := mc.appConfig.GetListenAddr(mc.capability); err == nil && (ep == nil || newAddr != ep.Address) {
			if host, port, splitErr := net.SplitHostPort(newAddr); splitErr == nil {
				mc.UpdateEndpoint(host, port)
				ep = mc.endpoint.Load()
			}
		}
	}
	return ep
}

// -----------------------------------------------------------------------------

// Write sends data over the connection, lock-free on the hot path.
func (mc *ManagedConnection) Write(p []byte) (n int, err error) {
	connPtr := mc.currentConn.Load()
	if connPtr == nil || *connPtr == nil {
		if err := mc.reconnect(); err != nil {
			return 0, err
		}
		connPtr = mc.currentConn.Load()
		if connPtr == nil || *connPtr == nil {
			return 0, io.ErrClosedPipe
		}
	}

	n, err = (*connPtr).Write(p)
	if err == nil {
		return n, nil
	}

	// Partial-write guard: if n > 0 bytes already left the process before failing,
	// re-sending full buffer p would corrupt framed protocols. Close & invalidate only.
	if n > 0 {
		mc.nm.Logger.Error("ManagedConnection: Partial write (%d/%d bytes) failed (%v). Closing corrupted stream without replay.", n, len(p), err)
		if mc.currentConn.CompareAndSwap(connPtr, nil) && *connPtr != nil {
			_ = (*connPtr).Close()
		}
		return n, fmt.Errorf("%w: partial write (%d/%d bytes) cannot safely auto-retry: %v", ErrWriteFailed, n, len(p), err)
	}

	// Hot-path recovery (n == 0): atomically clear only the failed socket, reconnect, and retry once
	mc.nm.Logger.Warning("ManagedConnection: Write failed (%v). Reconnecting...", err)
	if mc.currentConn.CompareAndSwap(connPtr, nil) && *connPtr != nil {
		_ = (*connPtr).Close()
	}
	if rErr := mc.reconnect(); rErr != nil {
		return 0, fmt.Errorf("%w: base write error: %v; reconnect error: %v", ErrWriteFailed, err, rErr)
	}
	connPtr = mc.currentConn.Load()
	if connPtr != nil && *connPtr != nil {
		return (*connPtr).Write(p)
	}
	return 0, ErrWriteFailed
}

func (mc *ManagedConnection) isClosing() bool {
	if mc.closing == nil {
		return false
	}
	select {
	case <-mc.closing:
		return true
	default:
		return false
	}
}

// -----------------------------------------------------------------------------

// Close terminates the connection and stops the reconnection loop.
func (mc *ManagedConnection) Close() error {
	mc.closeOnce.Do(func() {
		if mc.closing != nil {
			close(mc.closing)
		}
	})

	connPtr := mc.currentConn.Swap(nil)
	if connPtr != nil && *connPtr != nil {
		return (*connPtr).Close()
	}
	return nil
}

// -----------------------------------------------------------------------------

func (mc *ManagedConnection) reconnect() error {
	mc.reconnectMu.Lock()
	defer mc.reconnectMu.Unlock()

	// Double-check if another goroutine already restored the connection
	if connPtr := mc.currentConn.Load(); connPtr != nil && *connPtr != nil {
		return nil
	}

	nm := mc.nm
	var lastErr error

	for i := 0; (nm.MaxRetries == -1) || (i < nm.MaxRetries); i++ {
		if mc.isClosing() {
			return fmt.Errorf("connection closed")
		}

		attempt := i + 1
		ep := mc.currentEndpoint()
		conn, err := nm.EstablishConnection(ep)
		if err == nil {
			if mc.isClosing() {
				_ = conn.Close()
				return fmt.Errorf("connection closed")
			}
			nm.Logger.Info("ManagedConnection: Reconnected to %s", ep.Address)
			old := mc.currentConn.Swap(&conn)
			if old != nil && *old != nil {
				_ = (*old).Close()
			}
			if mc.isClosing() {
				if swapped := mc.currentConn.Swap(nil); swapped != nil && *swapped != nil {
					_ = (*swapped).Close()
				}
				return fmt.Errorf("connection closed")
			}
			return nil
		}
		lastErr = err

		if nm.OnError != nil {
			nm.OnError(attempt, err, "NetworkManager", fmt.Sprintf("Failed to recover connection to %s", ep.Address))
		}

		delay := nm.GetNextDelay(i)
		nm.Logger.Warning("ManagedConnection: Reconnect to %s failed: %v. Retrying in %v...", ep.Address, err, delay)

		select {
		case <-mc.closing:
			return fmt.Errorf("connection closed during retry sleep")
		case <-time.After(delay):
		}
	}

	ep := mc.currentEndpoint()
	return fmt.Errorf("%w: reached max retries %d for %s (last error: %v)", ErrMaxRetriesReached, nm.MaxRetries, ep.Address, lastErr)
}
