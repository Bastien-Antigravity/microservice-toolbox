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
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
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
