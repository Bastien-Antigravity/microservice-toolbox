package connectivity

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestResolver_ResolveBindAddr(t *testing.T) {
	// Test Case 1: Native Mode (Not Docker)
	r := &Resolver{IsDocker: false}
	addr, err := r.ResolveBindAddr("127.0.0.1")
	assert.NoError(t, err)
	assert.Equal(t, "127.0.0.1", addr, "Native mode should allow loopback")

	addr, err = r.ResolveBindAddr("1.2.3.4")
	assert.NoError(t, err)
	assert.Equal(t, "1.2.3.4", addr, "Native mode should allow external IP")

	// Test Case 2: Docker Mode + Loopback
	r = &Resolver{IsDocker: true}
	// Note: Mocking getPrimaryInterfaceIP is hard without refactoring to interface,
	// but we can check if it attempts to resolve loopback.
	// Since we can't easily mock network interfaces in unit tests, we'll check the logic flow.

	addr, err = r.ResolveBindAddr("1.2.3.4")
	assert.NoError(t, err)
	assert.Equal(t, "1.2.3.4", addr, "Docker mode should allow external IP directly")

	// Test Case 3: isLoopback
	assert.True(t, r.isLoopback("127.0.0.1"))
	assert.True(t, r.isLoopback("127.255.255.255"))
	assert.True(t, r.isLoopback("::1"))
	assert.True(t, r.isLoopback("localhost"))
	assert.False(t, r.isLoopback("8.8.8.8"))
}

func TestNewResolver(t *testing.T) {
	// Mocking environment variable
	os.Setenv("DOCKER_ENV", "true")
	defer os.Unsetenv("DOCKER_ENV")

	r := NewResolver()
	assert.True(t, r.IsDocker, "Should detect Docker from OS environment variable")
}
