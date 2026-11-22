package wiretap

import (
	"strings"
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

	// Verify ShouldSample and SetWebHubURL parity
	SetWebHubURL("http://127.0.0.1:5000/")
	if got := GetWebHubURL(); got != "http://127.0.0.1:5000" {
		t.Fatalf("expected trimmed hub URL, got %q", got)
	}
	if !ShouldSample(0) {
		t.Fatalf("expected ShouldSample(0) == true")
	}
	sampled := 0
	for i := 0; i < 16; i++ {
		if ShouldSample(0x3) {
			sampled++
		}
	}
	if sampled != 4 {
		t.Fatalf("expected 4 samples for mask 0x3 over 16 calls, got %d", sampled)
	}
}

func TestWireTapSanitizePayloadSummary_RedactionAndTruncation(t *testing.T) {
	Reset()
	defer func() {
		SetEnabled(true)
		Reset()
	}()
	SetEnabled(true)

	// 1. Direct helper check for ENC(...) redaction
	rawWithSecrets := "auth_header=ENC(super_secret_rsa_payload_123) secondary=ENC(another_secret) status=ok"
	sanitized := SanitizePayloadSummary(rawWithSecrets)
	expectedSanitized := "auth_header=ENC([REDACTED]) secondary=ENC([REDACTED]) status=ok"
	if sanitized != expectedSanitized {
		t.Fatalf("expected %q, got %q", expectedSanitized, sanitized)
	}
	if strings.Contains(sanitized, "super_secret") || strings.Contains(sanitized, "another_secret") {
		t.Fatalf("secret leaked in sanitized output: %q", sanitized)
	}

	// 2. Direct helper check for 256-byte cap with "..."
	longPayload := strings.Repeat("A", 400)
	truncated := SanitizePayloadSummary(longPayload)
	if len(truncated) != MaxPayloadSummaryBytes {
		t.Fatalf("expected truncated length %d, got %d", MaxPayloadSummaryBytes, len(truncated))
	}
	if !strings.HasSuffix(truncated, "...") {
		t.Fatalf("expected truncated payload to end with '...', got %q", truncated)
	}

	// 3. Verify RecordEventWithConnDelta and MergeRemoteSnapshot both apply sanitization
	RecordEvent(
		"config_server",
		"api_gateway",
		"GRPC",
		"HTTP/2 Protobuf",
		"config:push",
		"rpc",
		"outbound",
		"db_pass=ENC(top_secret_value) "+strings.Repeat("X", 300),
		512,
		1.0,
		false,
		false,
	)

	MergeRemoteSnapshot([]EdgeReport{
		{
			Source:      "secret_manager",
			Target:      "execution_engine",
			Protocol:    "GRPC",
			Framing:     "HTTP/2 Protobuf",
			ActiveConns: 1,
			TotalFrames: 1,
			TotalBytes:  512,
			Channels: []ChannelMetric{
				{
					Channel:     "secret:fetch",
					Category:    "rpc",
					Direction:   "outbound",
					Frames:      1,
					Bytes:       512,
					LastPayload: "api_key=ENC(merged_secret_key) " + strings.Repeat("Y", 300),
				},
			},
		},
	})

	snap := Snapshot()
	if len(snap) != 2 {
		t.Fatalf("expected 2 edges in snapshot, got %d", len(snap))
	}

	for _, edge := range snap {
		if len(edge.Channels) != 1 {
			t.Fatalf("expected 1 channel on edge %s->%s", edge.Source, edge.Target)
		}
		gotPayload := edge.Channels[0].LastPayload
		if len(gotPayload) != MaxPayloadSummaryBytes {
			t.Errorf("expected payload capped to %d bytes on %s->%s, got %d", MaxPayloadSummaryBytes, edge.Source, edge.Target, len(gotPayload))
		}
		if !strings.HasSuffix(gotPayload, "...") {
			t.Errorf("expected '...' suffix on truncated payload for %s->%s, got %q", edge.Source, edge.Target, gotPayload)
		}
		if !strings.Contains(gotPayload, "ENC([REDACTED])") {
			t.Errorf("expected ENC([REDACTED]) in payload for %s->%s, got %q", edge.Source, edge.Target, gotPayload)
		}
		if strings.Contains(gotPayload, "top_secret_value") || strings.Contains(gotPayload, "merged_secret_key") {
			t.Errorf("plaintext secret token leaked in %s->%s: %q", edge.Source, edge.Target, gotPayload)
		}
	}
}
