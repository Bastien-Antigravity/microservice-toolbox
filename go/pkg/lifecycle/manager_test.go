package lifecycle

import (
	"context"
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
}
