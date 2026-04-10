package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestDockerGuard(t *testing.T) {
	// Setup Resolver in Docker Mode
	ac, _ := LoadConfig("standalone", nil)
	ac.Resolver.IsDocker = true

	// Simulate CLI flags --host 1.2.3.4 --port 9999
	os.Args = []string{"test_app", "--host", "1.2.3.4", "--port", "9999"}

	args := ac.ParseCLIArgs(nil)

	// Verify they are ignored in Docker mode
	assert.Equal(t, "", args.Host, "Host should be ignored in Docker mode")
	assert.Equal(t, 0, args.Port, "Port should be ignored in Docker mode")
}

func TestNativeMode(t *testing.T) {
	// Setup Resolver in Native Mode
	ac, _ := LoadConfig("standalone", nil)
	ac.Resolver.IsDocker = false

	// Simulate CLI flags --host 1.2.3.4 --port 9999
	os.Args = []string{"test_app", "--host", "1.2.3.4", "--port", "9999"}

	args := ac.ParseCLIArgs(nil)

	// Verify they are accepted in Native mode
	assert.Equal(t, "1.2.3.4", args.Host)
	assert.Equal(t, 9999, args.Port)
}
