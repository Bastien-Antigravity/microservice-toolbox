// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Resolves capability network addresses and applies Docker Guard suppression rules.
//
// DATA FLOW:
// Capability Query -> Address Resolution + Docker Guard -> Final Bind Address
//
// KEY PARAMETERS:
// - capability: Service name to resolve.
// - Docker Guard: Suppresses localhost to 0.0.0.0 in container environments.
// -----------------------------------------------------------------------------

package connectivity

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestResolver_ResolveBindAddr(t *testing.T) {
	// Test Case 1: Native Mode relies strictly on configured IP
	r := &Resolver{IsDocker: false}
	addr, err := r.ResolveBindAddr("127.0.0.1")
	assert.NoError(t, err)
	assert.Equal(t, "127.0.0.1", addr)

	addr, err = r.ResolveBindAddr("1.2.3.4")
	assert.NoError(t, err)
	assert.Equal(t, "1.2.3.4", addr)

	// Test Case 2: Docker Mode ALSO honors config address (no hardcoded 0.0.0.0 override)
	r = &Resolver{IsDocker: true}
	addr, err = r.ResolveBindAddr("10.1.2.3")
	assert.NoError(t, err)
	assert.Equal(t, "10.1.2.3", addr)

	fullDocker, err := r.ResolveFullBindAddr("[::1]:8080")
	assert.NoError(t, err)
	assert.Equal(t, "[::1]:8080", fullDocker)

	// Test Case 3: Fail-fast on empty IP / empty host / empty port
	_, err = r.ResolveBindAddr("")
	assert.Error(t, err)
	_, err = r.ResolveFullBindAddr(":8080")
	assert.Error(t, err)
	_, err = r.ResolveFullBindAddr("127.0.0.1:")
	assert.Error(t, err)

	// Test Case 4: isLoopback / IsLoopback & IPv6 parity
	assert.True(t, r.IsLoopback("127.0.0.1"))
	assert.True(t, r.isLoopback("127.255.255.255"))
	assert.True(t, r.isLoopback("::1"))
	assert.True(t, r.isLoopback("LocalHost"))
	assert.False(t, r.isLoopback("8.8.8.8"))

	native := &Resolver{IsDocker: false}
	bareV6, err := native.ResolveFullBindAddr("::1")
	assert.NoError(t, err)
	assert.Equal(t, "::1", bareV6)
}

func TestNewResolver(t *testing.T) {
	// Mocking environment variable
	_ = os.Setenv("DOCKER_ENV", "true")
	defer func() { _ = os.Unsetenv("DOCKER_ENV") }()

	r := NewResolver()
	assert.True(t, r.IsDocker, "Should detect Docker from OS environment variable")
}
