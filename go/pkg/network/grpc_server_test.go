package network

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNewGRPCServer_DockerGuard(t *testing.T) {
	// 1. Test Native Mode (Docker off)
	_ = os.Unsetenv("DOCKER_ENV")
	s1 := NewGRPCServer("127.0.0.1:50051")
	assert.Equal(t, "127.0.0.1:50051", s1.Addr)

	// 2. Test Docker Mode (Forced via ENV)
	_ = os.Setenv("DOCKER_ENV", "true")
	defer os.Unsetenv("DOCKER_ENV")

	s2 := NewGRPCServer("127.0.0.1:50051")
	// Should be suppressed to 0.0.0.0:50051
	assert.Equal(t, "0.0.0.0:50051", s2.Addr)

	s3 := NewGRPCServer("10.0.0.5:8080")
	// Even external IPs should be suppressed to 0.0.0.0 in Docker per requirement
	assert.Equal(t, "0.0.0.0:8080", s3.Addr)
}
