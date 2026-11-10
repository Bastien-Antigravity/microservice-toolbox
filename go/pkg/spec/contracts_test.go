package spec

import (
	"strings"
	"testing"

	config_schemas "github.com/Bastien-Antigravity/distributed-config/src/schemas"
)

func TestExtractProtoTextAndCapnpAndRenderProtoIDL(t *testing.T) {
	sampleProto := `syntax = "proto3";
package demo;
service DemoService {
  rpc Ping (PingReq) returns (PingResp);
  rpc StreamData (stream Req) returns (stream Resp);
}`
	ops := ExtractProtoTextOperations(sampleProto)
	if len(ops) != 2 {
		t.Fatalf("expected 2 RPC operations, got %d", len(ops))
	}
	if ops[0].Kind != "RPC" || ops[0].Target != "demo.DemoService/Ping" {
		t.Fatalf("unexpected first op: %+v", ops[0])
	}
	if ops[1].Kind != "BIDI_STREAM" || ops[1].Input != "stream Req" || ops[1].Output != "stream Resp" {
		t.Fatalf("unexpected streaming op: %+v", ops[1])
	}

	sampleCapnp := `
enum Level {
  info @0;
  error @1;
}
struct Packet {
  id @0 :Text;
  payload @1 :Data;
}`
	capOps := ExtractCapnpOperations(sampleCapnp)
	if len(capOps) != 2 {
		t.Fatalf("expected 2 capnp items, got %d", len(capOps))
	}
	if capOps[0].Kind != "ENUM" || capOps[1].Kind != "STRUCT" {
		t.Fatalf("unexpected capnp operations: %+v", capOps)
	}

	rendered := RenderProtoIDL((&config_schemas.ConfigMsg{}).ProtoReflect().Descriptor().ParentFile())
	if !strings.Contains(rendered, "message ConfigMsg") || !strings.Contains(rendered, "FULL_REFRESH") {
		t.Fatalf("expected rendered ConfigMsg IDL, got: %s", rendered)
	}

	env := NewContractsEnvelope("test_svc", "1.0.0", "unit test", []ExchangeContract{{ID: "rest", Type: "HTTP/REST"}})
	if !env.Reliable || !env.Exhaustive || len(env.Contracts) != 1 {
		t.Fatalf("unexpected envelope: %+v", env)
	}
}

