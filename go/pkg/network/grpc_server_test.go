// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Configures and launches gRPC servers with Docker Guard address binding rules.
//
// DATA FLOW:
// Listen Address -> Docker Guard Resolver -> gRPC Listener
//
// KEY PARAMETERS:
// - addr: Configured host:port listen string.
// -----------------------------------------------------------------------------

package network

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNewGRPCServer_ConfigAddressPreserved(t *testing.T) {
	// 1. Test Native Mode
	_ = os.Unsetenv("DOCKER_ENV")
	s1 := NewGRPCServer("127.0.0.1:50051")
	assert.Equal(t, "127.0.0.1:50051", s1.Addr)

	// 2. Test Docker Mode also preserves configured address (zero hardcoded 0.0.0.0 override)
	_ = os.Setenv("DOCKER_ENV", "true")
	defer os.Unsetenv("DOCKER_ENV")

	s2 := NewGRPCServer("127.0.0.1:50051")
	assert.Equal(t, "127.0.0.1:50051", s2.Addr)

	s3 := NewGRPCServer("10.0.0.5:8080")
	assert.Equal(t, "10.0.0.5:8080", s3.Addr)

	assert.Panics(t, func() {
		NewGRPCServer("")
	})
}
