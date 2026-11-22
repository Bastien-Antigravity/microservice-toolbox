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
// - HookTimeout: Maximum duration allowed per cleanup hook before advancing.
// -----------------------------------------------------------------------------

package lifecycle

import (
	"context"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
)

// DefaultHookTimeout is the default maximum duration allowed for a single cleanup hook.
const DefaultHookTimeout = 10 * time.Second

// ShutdownFunc is a function called during graceful shutdown.
type ShutdownFunc func() error

type cleanupHook struct {
	name string
	fn   ShutdownFunc
}

// -----------------------------------------------------------------------------
// Manager handles application lifecycle and graceful shutdown.
type Manager struct {
	mu          sync.Mutex
	cleanups    []cleanupHook
	Logger      logger.Logger
	HookTimeout time.Duration
}

// NewManager creates a new lifecycle manager with default logging.
func NewManager() *Manager {
	return NewManagerWithLogger(nil)
}

// NewManagerWithLogger creates a new lifecycle manager with an explicit logger.
func NewManagerWithLogger(l logger.Logger) *Manager {
	return &Manager{
		cleanups:    make([]cleanupHook, 0),
		Logger:      logger.EnsureSafeLogger(l),
		HookTimeout: DefaultHookTimeout,
	}
}

// -----------------------------------------------------------------------------
// Register adds a named cleanup function to the shutdown sequence safely under mutex.
func (m *Manager) Register(name string, fn ShutdownFunc) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.cleanups = append(m.cleanups, cleanupHook{name: name, fn: fn})
}

// ExecuteCleanups runs all registered cleanup hooks in LIFO order and drains the hook list.
func (m *Manager) ExecuteCleanups() {
	m.mu.Lock()
	hooks := m.cleanups
	m.cleanups = nil
	timeout := m.HookTimeout
	m.mu.Unlock()

	log := logger.EnsureSafeLogger(m.Logger)

	for i := len(hooks) - 1; i >= 0; i-- {
		hook := hooks[i]
		log.Info("Lifecycle: Executing cleanup hook [%s]...", hook.name)
		if timeout > 0 {
			done := make(chan error, 1)
			go func(fn ShutdownFunc) {
				done <- fn()
			}(hook.fn)

			timer := time.NewTimer(timeout)
			select {
			case err := <-done:
				timer.Stop()
				if err != nil {
					log.Error("Lifecycle: Cleanup hook [%s] failed: %v", hook.name, err)
				}
			case <-timer.C:
				log.Error("Lifecycle: Cleanup hook [%s] timed out after %v; advancing to remaining hooks", hook.name, timeout)
			}
		} else {
			if err := hook.fn(); err != nil {
				log.Error("Lifecycle: Cleanup hook [%s] failed: %v", hook.name, err)
			}
		}
	}
	log.Info("Lifecycle: Clean shutdown completed.")
}

// Wait blocks until a SIGINT or SIGTERM is received or context is cancelled,
// then executes all registered cleanups in reverse registration order (LIFO).
func (m *Manager) Wait(ctx context.Context) {
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(stop)

	select {
	case sig := <-stop:
		m.Logger.Info("Lifecycle: Received signal %v. Initiating graceful shutdown...", sig)
	case <-ctx.Done():
		m.Logger.Info("Lifecycle: Context canceled. Initiating graceful shutdown...")
	}

	m.ExecuteCleanups()
}
