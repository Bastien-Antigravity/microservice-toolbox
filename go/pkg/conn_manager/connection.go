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
	"strings"
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

// NewEndpoint builds and validates an immutable Endpoint on the cold path.
func NewEndpoint(ip, port, publicIP, profile string) *Endpoint {
	cleanIP := strings.Trim(ip, "\"")
	cleanPort := strings.Trim(port, "\"")
	cleanPubIP := strings.Trim(publicIP, "\"")
	cleanProfile := strings.Trim(profile, "\"")
	return &Endpoint{
		IP:       cleanIP,
		Port:     cleanPort,
		PublicIP: cleanPubIP,
		Profile:  cleanProfile,
		Address:  cleanIP + ":" + cleanPort,
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
	onReload    atomic.Pointer[ReloadHandler]
	reconnectMu sync.Mutex
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
		if nm.OnReloadConfig != nil {
			h := nm.OnReloadConfig
			mc.onReload.Store(&h)
		}
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

// SetReloadHandler sets the reload callback on ManagedConnection atomically.
func (mc *ManagedConnection) SetReloadHandler(handler ReloadHandler) {
	mc.onReload.Store(&handler)
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

func (mc *ManagedConnection) triggerReload(attempt int) {
	ac := mc.appConfig
	capName := mc.capability
	reloadPtr := mc.onReload.Load()

	// 1. Direct AppConfig resolution if bound to capability
	if ac != nil && capName != "" {
		mc.nm.Logger.Warning("ManagedConnection: 3 failed connection attempts reached (attempt %d). Synchronizing config from server...", attempt)
		_ = ac.Sync()
		newAddr, err := ac.GetListenAddr(capName)
		if err == nil {
			host, port, splitErr := net.SplitHostPort(newAddr)
			if splitErr == nil {
				mc.UpdateEndpoint(host, port)
				mc.nm.Logger.Info("ManagedConnection: Target address for capability %s updated to %s:%s following config sync", capName, host, port)
				return
			}
		}
		mc.nm.Logger.Warning("ManagedConnection: Config sync for capability %s returned error: %v", capName, err)
		return
	}

	// 2. Custom ReloadHandler callback fallback (for raw connections without AppConfig)
	var reloadFn ReloadHandler
	if reloadPtr != nil {
		reloadFn = *reloadPtr
	} else if mc.nm != nil {
		reloadFn = mc.nm.OnReloadConfig
	}
	if reloadFn == nil {
		return
	}

	mc.nm.Logger.Warning("ManagedConnection: 3 failed connection attempts reached (attempt %d). Reloading configuration...", attempt)
	newIP, newPort, err := reloadFn(attempt)
	if err != nil {
		mc.nm.Logger.Warning("ManagedConnection: Configuration reload returned error: %v", err)
		return
	}

	mc.UpdateEndpoint(newIP, newPort)
	mc.nm.Logger.Info("ManagedConnection: Target address updated to %s:%s following config reload", newIP, newPort)
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

	// Hot-path recovery: reconnect and retry once
	mc.nm.Logger.Warning("ManagedConnection: Write failed (%v). Reconnecting...", err)
	oldConn := mc.currentConn.Swap(nil)
	if oldConn != nil && *oldConn != nil {
		_ = (*oldConn).Close()
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
	select {
	case <-mc.closing:
		// Already closed
	default:
		close(mc.closing)
	}

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
		if attempt%3 == 0 {
			mc.triggerReload(attempt)
		}

		ep := mc.endpoint.Load()
		conn, err := nm.EstablishConnection(ep)
		if err == nil {
			nm.Logger.Info("ManagedConnection: Reconnected to %s", ep.Address)
			old := mc.currentConn.Swap(&conn)
			if old != nil && *old != nil {
				_ = (*old).Close()
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

	ep := mc.endpoint.Load()
	return fmt.Errorf("%w: reached max retries %d for %s (last error: %v)", ErrMaxRetriesReached, nm.MaxRetries, ep.Address, lastErr)
}
