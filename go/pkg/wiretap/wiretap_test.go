package wiretap

import (
	"testing"

	safesocket "github.com/Bastien-Antigravity/safe-socket"
)

func TestWireTapAtomicSwitchAndSegregatedChannels(t *testing.T) {
	Reset()
	defer func() {
		SetEnabled(false)
		Reset()
	}()

	SetLocalService("watchdog_agent")

	// 1. When disabled, neither wiretap nor safe-socket telemetry is active
	SetEnabled(false)
	if IsEnabled() || safesocket.IsTelemetryEnabled() {
		t.Fatalf("expected wiretap and safe-socket telemetry to be disabled")
	}

	RecordEvent(
		"watchdog_agent",
		"tele_remote",
		"GRPC",
		"HTTP/2 Protobuf (Stream)",
		"teleremote:registration",
		"registration",
		"outbound",
		"menu_sync",
		128,
		1.5,
		false,
		false,
	)
	if snap := Snapshot(); len(snap) != 0 {
		t.Fatalf("expected 0 edges while disabled, got %d", len(snap))
	}

	// 2. Enable atomically
	SetEnabled(true)
	if !IsEnabled() || !safesocket.IsTelemetryEnabled() {
		t.Fatalf("expected wiretap and safe-socket telemetry to be enabled")
	}

	// Record two distinct segregated channels on the same edge (watchdog_agent -> tele_remote)
	RecordEvent(
		"watchdog_agent",
		"tele_remote",
		"GRPC",
		"HTTP/2 Protobuf (Stream)",
		"teleremote:registration",
		"registration",
		"outbound",
		"menu_sync",
		256,
		1.2,
		false,
		false,
	)
	RecordEvent(
		"watchdog_agent",
		"tele_remote",
		"GRPC",
		"HTTP/2 Protobuf (Stream)",
		"teleremote:telemetry",
		"telemetry",
		"outbound",
		"All 11 services healthy",
		64,
		0.8,
		false,
		false,
	)

	// Record an external client connection (antigravity_ide -> rag_mcp)
	RecordEventWithConnDelta(
		"antigravity_ide",
		"rag_mcp",
		"SSE",
		"Port 8090 FastMCP (SSE/JSON-RPC)",
		"mcp:tool:query_ecosystem_graph",
		"mcp_tool",
		"inbound",
		"query_ecosystem_graph",
		512,
		4.0,
		false,
		true,
		1,
	)

	snap := Snapshot()
	if len(snap) != 2 {
		t.Fatalf("expected 2 edges in snapshot, got %d", len(snap))
	}

	// Edge 0: antigravity_ide -> rag_mcp (sorted alphabetically by source)
	if snap[0].Source != "antigravity_ide" || snap[0].Target != "rag_mcp" || !snap[0].IsExternal {
		t.Errorf("unexpected external edge[0]: %+v", snap[0])
	}
	if len(snap[0].Channels) != 1 || snap[0].Channels[0].Channel != "mcp:tool:query_ecosystem_graph" {
		t.Errorf("unexpected channels on edge[0]: %+v", snap[0].Channels)
	}

	// Edge 1: watchdog_agent -> tele_remote with 2 segregated channels
	if snap[1].Source != "watchdog_agent" || snap[1].Target != "tele_remote" || snap[1].TotalFrames != 2 || snap[1].TotalBytes != 320 {
		t.Errorf("unexpected edge[1]: %+v", snap[1])
	}
	if len(snap[1].Channels) != 2 {
		t.Fatalf("expected 2 segregated channels on watchdog_agent -> tele_remote, got %d", len(snap[1].Channels))
	}
	if snap[1].Channels[0].Channel != "teleremote:registration" || snap[1].Channels[1].Channel != "teleremote:telemetry" {
		t.Errorf("unexpected segregated channels: %+v", snap[1].Channels)
	}
}

