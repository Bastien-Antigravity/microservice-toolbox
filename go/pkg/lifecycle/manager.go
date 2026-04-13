package lifecycle

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/utils"
)

// ShutdownFunc is a function called during graceful shutdown.
type ShutdownFunc func() error

// Manager handles application lifecycle and graceful shutdown.
type Manager struct {
	cleanups []ShutdownFunc
	Logger   utils.Logger
}

// NewManager creates a new lifecycle manager with default logging.
func NewManager() *Manager {
	return NewManagerWithLogger(nil)
}

// NewManagerWithLogger creates a new lifecycle manager with an explicit logger.
func NewManagerWithLogger(logger utils.Logger) *Manager {
	return &Manager{
		cleanups: make([]ShutdownFunc, 0),
		Logger:   utils.EnsureSafeLogger(logger),
	}
}

// Register adds a cleanup function to the list.
func (m *Manager) Register(name string, fn ShutdownFunc) {
	m.cleanups = append(m.cleanups, fn)
}

// Wait blocks until a SIGINT or SIGTERM is received, then executes cleanups.
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
		if err := m.cleanups[i](); err != nil {
			m.Logger.Error("Lifecycle: Cleanup failed: %v", err)
		}
	}
	m.Logger.Info("Lifecycle: Clean shutdown completed.")
}
