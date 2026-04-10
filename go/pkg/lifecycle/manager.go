package lifecycle

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

// ShutdownFunc is a function called during graceful shutdown.
type ShutdownFunc func() error

// Manager handles application lifecycle and graceful shutdown.
type Manager struct {
	cleanups []ShutdownFunc
}

// NewManager creates a new lifecycle manager.
func NewManager() *Manager {
	return &Manager{
		cleanups: make([]ShutdownFunc, 0),
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
		fmt.Printf("\nLifecycle: Received signal %v. Initiating graceful shutdown...\n", sig)
	case <-ctx.Done():
		fmt.Printf("\nLifecycle: Context canceled. Initiating graceful shutdown...\n")
	}

	// Execute cleanups in reverse order (LIFO)
	for i := len(m.cleanups) - 1; i >= 0; i-- {
		if err := m.cleanups[i](); err != nil {
			fmt.Fprintf(os.Stderr, "Lifecycle: Cleanup failed: %v\n", err)
		}
	}
	fmt.Println("Lifecycle: Clean shutdown completed.")
}
