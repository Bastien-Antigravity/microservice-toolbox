package lifecycle

// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Manages application lifecycle, OS signal traps (SIGINT, SIGTERM), and orderly
// LIFO execution of registered graceful shutdown hooks.
//
// DATA FLOW:
// OS Signals / Context Cancel -> Manager.Wait() -> LIFO Cleanup Execution -> Process Exit
//
// KEY PARAMETERS:
// - cleanups: Slice of registered cleanupHook instances (executed LIFO).
// - Logger: Universal Logger instance for audit logging.
// -----------------------------------------------------------------------------

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
)

// ShutdownFunc is a function called during graceful shutdown.
type ShutdownFunc func() error

type cleanupHook struct {
	name string
	fn   ShutdownFunc
}

// Manager handles application lifecycle and graceful shutdown.
type Manager struct {
	cleanups []cleanupHook
	Logger   logger.Logger
}

// NewManager creates a new lifecycle manager with default logging.
func NewManager() *Manager {
	return NewManagerWithLogger(nil)
}

// NewManagerWithLogger creates a new lifecycle manager with an explicit logger.
func NewManagerWithLogger(l logger.Logger) *Manager {
	return &Manager{
		cleanups: make([]cleanupHook, 0),
		Logger:   logger.EnsureSafeLogger(l),
	}
}

// Register adds a named cleanup function to the shutdown sequence.
func (m *Manager) Register(name string, fn ShutdownFunc) {
	m.cleanups = append(m.cleanups, cleanupHook{name: name, fn: fn})
}

// Wait blocks until a SIGINT or SIGTERM is received or context is cancelled,
// then executes all registered cleanups in reverse registration order (LIFO).
func (m *Manager) Wait(ctx context.Context) {
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-stop:
		m.Logger.Info("Lifecycle: Received signal %v. Initiating graceful shutdown...", sig)
	case <-ctx.Done():
		m.Logger.Info("Lifecycle: Context canceled. Initiating graceful shutdown...")
	}

	// Execute cleanups in reverse order (LIFO)
	for i := len(m.cleanups) - 1; i >= 0; i-- {
		hook := m.cleanups[i]
		m.Logger.Info("Lifecycle: Executing cleanup hook [%s]...", hook.name)
		if err := hook.fn(); err != nil {
			m.Logger.Error("Lifecycle: Cleanup hook [%s] failed: %v", hook.name, err)
		}
	}
	m.Logger.Info("Lifecycle: Clean shutdown completed.")
}
