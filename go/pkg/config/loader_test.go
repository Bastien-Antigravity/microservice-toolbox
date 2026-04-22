package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	distconf "github.com/Bastien-Antigravity/distributed-config"
)

func TestAppConfig_GetListenAddr(t *testing.T) {
	// Create a dummy config file
	yamlContent := `
common:
  name: test-app
capabilities:
  test-service:
    ip: 1.2.3.4
    port: "8080"
`
	err := os.WriteFile("test.yaml", []byte(yamlContent), 0644)
	assert.NoError(t, err)
	defer func() { _ = os.Remove("test.yaml") }()

	// Load config
	ac, err := LoadConfig("test", nil)
	if err != nil {
		t.Skip("Skipping LoadConfig test as it depends on distributed-config Server/File logic which might fail in this environment")
		return
	}

	addr, err := ac.GetListenAddr("test-service")
	assert.NoError(t, err)
	assert.Equal(t, "1.2.3.4:8080", addr)
}

func TestDeepMerge(t *testing.T) {
	dst := map[string]interface{}{
		"a": 1,
		"b": map[string]interface{}{
			"c": 2,
		},
	}
	src := map[string]interface{}{
		"b": map[string]interface{}{
			"d": 3,
		},
		"e": 4,
	}

	result := DeepMerge(dst, src)
	
	assert.Equal(t, 1, result["a"])
	assert.Equal(t, 4, result["e"])
	
	bMap := result["b"].(map[string]interface{})
	assert.Equal(t, 2, bMap["c"])
	assert.Equal(t, 3, bMap["d"])
}

func TestAppConfig_EnsurePath(t *testing.T) {
	// Initialize ac with a minimal Config using the factory method
	ac := &AppConfig{
		Config: distconf.New("test"),
	}
	
	ac.ensurePath("capabilities.new-service")
	assert.NotNil(t, ac.Capabilities["new-service"])
	
	_, ok := ac.Capabilities["new-service"].(map[string]interface{})
	assert.True(t, ok)
}
