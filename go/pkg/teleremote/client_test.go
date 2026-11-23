// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for TeleClient action tree generation, menu JSON serialization, and handler dispatching.
//
// DATA FLOW:
// Action Definitions -> TeleClient -> GenerateMenuJSON() -> JSON Assertion
//
// KEY PARAMETERS:
// - None (Unit Test Suite).
// -----------------------------------------------------------------------------

package teleremote

import (
	"crypto/tls"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

	distconf "github.com/Bastien-Antigravity/distributed-config"
)

func TestTeleClient_ActionAndMenuGeneration(t *testing.T) {
	client := NewTeleClient("TestApp", "127.0.0.1", 1863, nil)

	h1Called := false
	a1 := Action{
		Label: "Command 1",
		Callback: func(input string) error {
			h1Called = true
			return nil
		},
	}

	h2Called := false
	subA := Action{
		Label:       "Sub Command",
		InputPrompt: "Enter text:",
		Callback: func(input string) error {
			h2Called = true
			return nil
		},
	}
	a2 := Action{
		Label:   "Menu 1",
		SubMenu: []Action{subA},
	}

	client.AddAction(a1)
	client.AddAction(a2)

	// Verify handler registration
	client.mu.RLock()
	_, hasH1 := client.handlers["Command 1"]
	_, hasSub := client.handlers["Sub Command"]
	_, hasMenu := client.handlers["Menu 1"]
	client.mu.RUnlock()

	assert.True(t, hasH1)
	assert.True(t, hasSub)
	assert.False(t, hasMenu) // Submenu has no callback

	// Verify executing handlers directly
	err := client.handlers["Command 1"]("")
	assert.NoError(t, err)
	assert.True(t, h1Called)

	err = client.handlers["Sub Command"]("test input")
	assert.NoError(t, err)
	assert.True(t, h2Called)

	// Verify Menu JSON serialization
	menuJSON := client.GenerateMenuJSON()
	var rows []rowDef
	err = json.Unmarshal([]byte(menuJSON), &rows)
	assert.NoError(t, err)
	assert.Len(t, rows, 2)

	// Check leaf button
	btn1 := rows[0].Buttons[0]
	assert.Equal(t, "Command 1", btn1.Label)
	assert.Equal(t, int32(99), btn1.CmdType)
	assert.Equal(t, "Command 1", btn1.Payload)
	assert.Empty(t, btn1.InputPrompt)
	assert.Empty(t, btn1.Menu)

	// Check submenu button
	btn2 := rows[1].Buttons[0]
	assert.Equal(t, "Menu 1", btn2.Label)
	assert.Equal(t, int32(0), btn2.CmdType)
	assert.Empty(t, btn2.Payload)
	assert.Len(t, btn2.Menu, 1)

	subBtn := btn2.Menu[0].Buttons[0]
	assert.Equal(t, "Sub Command", subBtn.Label)
	assert.Equal(t, "Enter text:", subBtn.InputPrompt)
	assert.Equal(t, int32(99), subBtn.CmdType)
	assert.Equal(t, "Sub Command", subBtn.Payload)
}

func TestTeleClient_UpdateActions(t *testing.T) {
	client := NewTeleClient("TestApp", "127.0.0.1", 1863, nil)

	a1 := Action{
		Label:    "Initial",
		Callback: func(input string) error { return nil },
	}
	client.AddAction(a1)

	client.mu.RLock()
	assert.Len(t, client.actions, 1)
	assert.Contains(t, client.handlers, "Initial")
	client.mu.RUnlock()

	a2 := Action{
		Label:    "Replaced",
		Callback: func(input string) error { return nil },
	}
	client.UpdateActions([]Action{a2})

	client.mu.RLock()
	assert.Len(t, client.actions, 1)
	assert.NotContains(t, client.handlers, "Initial")
	assert.Contains(t, client.handlers, "Replaced")
	client.mu.RUnlock()
}

func TestTeleClient_SendTelemetryDisconnected(t *testing.T) {
	client := NewTeleClient("TestApp", "127.0.0.1", 1863, nil)
	err := client.SendTelemetry("test message")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not connected to tele-remote")
}

func TestGenerateMenuJSON_WithPriorityAndOrder(t *testing.T) {
	client := NewTeleClient("TestApp", "127.0.0.1", 1863, nil)
	client.UpdateActions([]Action{
		{
			Label:    "Second",
			Order:    20,
			Callback: func(input string) error { return nil },
		},
		{
			Label: "First Menu",
			Order: 10,
			SubMenu: []Action{
				{
					Label:    "Sub Item",
					Order:    5,
					Callback: func(input string) error { return nil },
				},
			},
		},
	})

	// Default priority == 0 emits flat JSON array for backward compatibility
	defaultJSON := client.GenerateMenuJSON()
	var flatRows []rowDef
	require.NoError(t, json.Unmarshal([]byte(defaultJSON), &flatRows))
	require.Len(t, flatRows, 2)
	assert.Equal(t, 20, flatRows[0].Order)
	assert.Equal(t, 20, flatRows[0].Buttons[0].Order)
	assert.Equal(t, 10, flatRows[1].Order)
	assert.Equal(t, 10, flatRows[1].Buttons[0].Order)
	require.Len(t, flatRows[1].Buttons[0].Menu, 1)
	assert.Equal(t, 5, flatRows[1].Buttons[0].Menu[0].Order)
	assert.Equal(t, 5, flatRows[1].Buttons[0].Menu[0].Buttons[0].Order)

	// Priority > 0 emits OpenMFE wrapper object {"priority": ..., "rows": [...]}
	returned := client.SetPriority(20)
	assert.Same(t, client, returned)

	wrappedJSON := client.GenerateMenuJSON()
	var envelope struct {
		Priority int      `json:"priority"`
		Rows     []rowDef `json:"rows"`
	}
	require.NoError(t, json.Unmarshal([]byte(wrappedJSON), &envelope))
	assert.Equal(t, 20, envelope.Priority)
	require.Len(t, envelope.Rows, 2)
	assert.Equal(t, 20, envelope.Rows[0].Buttons[0].Order)
	assert.Equal(t, 10, envelope.Rows[1].Buttons[0].Order)
}

func TestTeleClient_ConfigureFromAppConfig_LocalTLSAndPolicy(t *testing.T) {
	dist := distconf.New("standalone")
	dist.Capabilities = map[string]interface{}{
		"tele_remote": map[string]interface{}{
			"tls_enabled":      true,
			"tls_mode":         "auto",
			"auth_token":       "secret-tok",
			"tls_cert_file":    "/ignored/from-capabilities.crt",
			"tls_key_file":     "/ignored/from-capabilities.key",
			"private_key_path": "/ignored/legacy-key.pem",
		},
		"my_service": map[string]interface{}{
			"tls": map[string]interface{}{
				"cert_file": "/ignored/cap-service.crt",
				"key_file":  "/ignored/cap-service.key",
				"ca_file":   "/ignored/cap-service-ca.crt",
			},
		},
	}
	ac := &toolbox_config.AppConfig{
		Config: dist,
		Local: map[string]interface{}{
			"my_service": map[string]interface{}{
				"tls": map[string]interface{}{
					"cert_file": "/etc/bastien/certs/my_service.crt",
					"key_file":  "/etc/bastien/certs/my_service.key",
					"ca_file":   "/etc/bastien/certs/fleet-ca.crt",
				},
			},
		},
	}

	client := NewTeleClient("MyService", "10.0.0.5", 1863, nil)
	err := client.ConfigureFromAppConfig(ac, "my_service")
	require.NoError(t, err)

	client.mu.RLock()
	assert.Equal(t, toolbox_config.LocalTLSConfig{
		CertFile: "/etc/bastien/certs/my_service.crt",
		KeyFile:  "/etc/bastien/certs/my_service.key",
		CAFile:   "/etc/bastien/certs/fleet-ca.crt",
	}, client.localTLS)
	assert.True(t, client.tlsEnabled)
	assert.Equal(t, "auto", client.tlsMode)
	assert.Equal(t, "secret-tok", client.authToken)
	client.mu.RUnlock()

	t.Run("string tls_enabled and live config update", func(t *testing.T) {
		dist.ReplaceLive(map[string]map[string]string{
			"tele_remote": {
				"tls_enabled": "false",
				"tls_mode":    "STRICT",
				"auth_token":  "updated-tok",
			},
		})
		ac.Local["my_service"] = map[string]interface{}{
			"tls": map[string]interface{}{
				"cert_file": "/etc/bastien/certs/rotated.crt",
				"key_file":  "/etc/bastien/certs/rotated.key",
				"ca_file":   "/etc/bastien/certs/rotated-ca.crt",
			},
		}
		require.NotNil(t, dist.ParentOnLiveConfUpdate)
		dist.ParentOnLiveConfUpdate(nil)

		client.mu.RLock()
		assert.False(t, client.tlsEnabled)
		assert.Equal(t, "strict", client.tlsMode)
		assert.Equal(t, "updated-tok", client.authToken)
		assert.Equal(t, toolbox_config.LocalTLSConfig{
			CertFile: "/etc/bastien/certs/rotated.crt",
			KeyFile:  "/etc/bastien/certs/rotated.key",
			CAFile:   "/etc/bastien/certs/rotated-ca.crt",
		}, client.localTLS)
		client.mu.RUnlock()
	})

	t.Run("fail fast when DecryptSecret fails on ENC auth_token", func(t *testing.T) {
		badDist := distconf.New("standalone")
		badDist.Capabilities = map[string]interface{}{
			"tele_remote": map[string]interface{}{
				"tls_enabled": "true",
				"tls_mode":    "auto",
				"auth_token":  "ENC(not-valid-base64-or-key)",
			},
		}
		badAC := &toolbox_config.AppConfig{Config: badDist}
		badClient := NewTeleClient("MyService", "10.0.0.5", 1863, nil)
		err := badClient.ConfigureFromAppConfig(badAC, "my_service")
		assert.Error(t, err)
	})
}

func TestTeleClient_SettersAndTLSPolicy(t *testing.T) {
	client := NewTeleClient("TestApp", "10.0.0.5", 1863, nil)
	customTLS := &tls.Config{MinVersion: tls.VersionTLS13}
	localCfg := toolbox_config.LocalTLSConfig{
		CertFile: " /certs/client.crt ",
		KeyFile:  " /certs/client.key ",
		CAFile:   " /certs/ca.crt ",
	}

	assert.Same(t, client, client.SetAuthToken("  secret-123  "))
	assert.Same(t, client, client.SetLocalTLS(localCfg))
	assert.Same(t, client, client.SetTLSPolicy(true, "STRICT"))
	assert.Same(t, client, client.SetTLSConfig(customTLS))
	assert.Same(t, client, client.SetPriority(25))

	client.mu.RLock()
	assert.Equal(t, "secret-123", client.authToken)
	assert.Equal(t, toolbox_config.LocalTLSConfig{
		CertFile: "/certs/client.crt",
		KeyFile:  "/certs/client.key",
		CAFile:   "/certs/ca.crt",
	}, client.localTLS)
	assert.True(t, client.tlsEnabled)
	assert.Equal(t, "strict", client.tlsMode)
	assert.Equal(t, customTLS, client.tlsConfig)
	assert.Equal(t, 25, client.priority)
	client.mu.RUnlock()

	// Empty mode normalizes to "auto"
	client.SetTLSPolicy(false, "   ")
	client.mu.RLock()
	assert.False(t, client.tlsEnabled)
	assert.Equal(t, "auto", client.tlsMode)
	client.mu.RUnlock()
}
