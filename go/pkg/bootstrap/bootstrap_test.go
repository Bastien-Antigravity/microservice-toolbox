// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for Go bootstrap initialization, dynamic version resolution, and mission ID binding.
//
// DATA FLOW:
// Temporary YAML Fixture -> BootstrapServiceSafe -> Verified AppConfig & Logger
//
// KEY PARAMETERS:
// - None (Unit Test Suite).
// -----------------------------------------------------------------------------

package bootstrap

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/trace"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestBootstrapServiceSafe_InitializesFromTempYAML(t *testing.T) {
	tmpDir := t.TempDir()
	yamlPath := filepath.Join(tmpDir, "standalone.yaml")
	yamlContent := `common:
  name: bootstrap-test-svc
capabilities:
  bootstrap-test-svc:
    ip: 127.0.0.1
    port: "19110"
  log_server:
    ip: 127.0.0.1
    port: "19111"
  web_interface:
    ip: 127.0.0.1
    port: "19112"
local:
  wiretap_enabled: false
  feature_flag: enabled
`
	require.NoError(t, os.WriteFile(yamlPath, []byte(yamlContent), 0644))

	t.Setenv("CONFIG_PATH", yamlPath)
	t.Setenv("CONFIG_PROFILE", "standalone")
	t.Setenv("LOGGER_PROFILE", "standard")
	t.Setenv("LOG_LEVEL", "INFO")
	t.Setenv(trace.EnvMissionID, "mission-bootstrap-123")

	appConfig, appLogger, err := BootstrapServiceSafe("bootstrap-test-svc")
	require.NoError(t, err)
	require.NotNil(t, appConfig)
	require.NotNil(t, appLogger)
	defer func() {
		if appConfig.Config != nil {
			appConfig.Close()
		}
	}()

	assert.Equal(t, "standalone", appConfig.Profile)
	assert.NotEmpty(t, appConfig.GetVersion())
	assert.Equal(t, "enabled", appConfig.GetLocalString("feature_flag"))

	addr, err := appConfig.GetListenAddr("bootstrap-test-svc")
	require.NoError(t, err)
	assert.Equal(t, "127.0.0.1:19110", addr)
}
