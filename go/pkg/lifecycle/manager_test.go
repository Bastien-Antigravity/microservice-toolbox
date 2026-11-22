// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Manages application lifecycle, OS signal traps (SIGINT, SIGTERM), and orderly LIFO cleanups.
//
// DATA FLOW:
// OS Signals / Context Cancel -> Manager.Wait() -> LIFO Cleanup Execution -> Process Exit
//
// KEY PARAMETERS:
// - cleanups: Slice of registered cleanupHook instances (executed LIFO).
// - Logger: Universal Logger instance for audit logging.
// -----------------------------------------------------------------------------

package lifecycle

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestManager_Lifecycle(t *testing.T) {
	m := NewManager()

	cleanupCalled := false
	m.Register("test_cleanup", func() error {
		cleanupCalled = true
		return nil
	})

	// Use a context to trigger shutdown
	ctx, cancel := context.WithCancel(context.Background())

	// Start Wait in a goroutine
	done := make(chan bool)
	go func() {
		m.Wait(ctx)
		done <- true
	}()

	// Simulate context cancellation
	cancel()

	select {
	case <-done:
		assert.True(t, cleanupCalled, "Cleanup function should have been called")
	case <-time.After(1 * time.Second):
		t.Fatal("Shutdown timed out")
	}

	// Verify explicit ExecuteCleanups runs LIFO and drains hooks
	m2 := NewManager()
	var order []string
	m2.Register("first", func() error { order = append(order, "first"); return nil })
	m2.Register("second", func() error { order = append(order, "second"); return nil })
	m2.ExecuteCleanups()
	assert.Equal(t, []string{"second", "first"}, order)
	m2.ExecuteCleanups()
	assert.Equal(t, []string{"second", "first"}, order)
}

func TestManager_HookTimeout_ContinuesLIFOExecution(t *testing.T) {
	m := NewManager()
	assert.Equal(t, 10*time.Second, m.HookTimeout, "Default HookTimeout should be 10s")

	m.HookTimeout = 30 * time.Millisecond

	var mu sync.Mutex
	var executed []string
	releaseHungHook := make(chan struct{})
	defer close(releaseHungHook)

	m.Register("first_SurvivingHook", func() error {
		mu.Lock()
		executed = append(executed, "first_SurvivingHook")
		mu.Unlock()
		return nil
	})

	m.Register("second_HungHook", func() error {
		mu.Lock()
		executed = append(executed, "second_HungHook_started")
		mu.Unlock()
		<-releaseHungHook
		return nil
	})

	m.Register("third_FastHook", func() error {
		mu.Lock()
		executed = append(executed, "third_FastHook")
		mu.Unlock()
		return nil
	})

	start := time.Now()
	m.ExecuteCleanups()
	elapsed := time.Since(start)

	if elapsed > 500*time.Millisecond {
		t.Fatalf("ExecuteCleanups took too long (%v), expected HookTimeout to unblock hung hook", elapsed)
	}

	mu.Lock()
	got := append([]string(nil), executed...)
	mu.Unlock()

	assert.Equal(t, []string{"third_FastHook", "second_HungHook_started", "first_SurvivingHook"}, got)
}
