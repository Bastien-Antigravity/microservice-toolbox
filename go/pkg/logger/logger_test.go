// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for EnsureSafeLogger, verifying safe no-op fallback in normal mode
// and strict panic enforcement in production/strict mode.
//
// DATA FLOW:
// Logger injection -> EnsureSafeLogger() -> Assertion
//
// KEY PARAMETERS:
// - STRICT_LOGGER: Environment variable toggling strict mode panic behavior.
// -----------------------------------------------------------------------------

package logger_test

import (
	"os"
	"testing"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
)

// -----------------------------------------------------------------------------

func TestEnsureSafeLogger_NormalFallback(t *testing.T) {
	_ = os.Unsetenv("STRICT_LOGGER")

	l := logger.EnsureSafeLogger(nil)
	if l == nil {
		t.Fatal("expected non-nil logger from EnsureSafeLogger")
	}

	// Calling methods on no-op logger must not panic
	l.Debug("test debug")
	l.Info("test info")
	l.Warning("test warning")
	l.Error("test error")
	l.Critical("test critical")
	l.AddMetadata("key", "val")
}

// -----------------------------------------------------------------------------

func TestEnsureSafeLogger_StrictModePanics(t *testing.T) {
	_ = os.Setenv("STRICT_LOGGER", "true")
	defer os.Unsetenv("STRICT_LOGGER")

	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected panic when STRICT_LOGGER=true and logger is nil")
		}
	}()

	_ = logger.EnsureSafeLogger(nil)
}

// -----------------------------------------------------------------------------

func TestEnsureSafeLogger_Passthrough(t *testing.T) {
	custom := &logger.FmtLogger{}
	l := logger.EnsureSafeLogger(custom)
	if l != custom {
		t.Fatalf("expected logger passthrough, got %v", l)
	}
}
