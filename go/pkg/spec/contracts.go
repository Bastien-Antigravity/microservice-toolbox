package spec

// =============================================================================
// ESSENTIAL PROCESS:
// Defines canonical, microservice-authored Exchange Contract models and helpers
// published via ServiceSpec and /api/v1/contracts endpoints. Enables reliable,
// exhaustive per-protocol inspection in OpenMFE Live Operations tabs.
//
// DATA FLOW:
// 1. Microservices embed raw schemas (.proto, .capnp, SQL DDL, REST routes, NATS
//    subjects) and build typed []ExchangeContract descriptors at runtime.
// 2. ServiceSpec publishes Contracts to web-interface POST /api/v1/register, and
//    HTTP services expose GET /api/v1/contracts directly from live handlers.
// 3. Frontend OpenMFE components render one tab per exchange contract type.
//
// KEY PARAMETERS:
// - ExchangeContract: Single typed protocol/channel contract owned by a service.
// - ContractsEnvelope: Standard HTTP JSON response returned by GET /api/v1/contracts.
// =============================================================================

import (
	"fmt"
	"net"
	"regexp"
	"strconv"
	"strings"
	"time"

	"google.golang.org/protobuf/reflect/protoreflect"
)

// -----------------------------------------------------------------------------

// ContractPeer identifies a collaborating microservice participating in an exchange contract.
type ContractPeer struct {
	Service     string `json:"service"`
	Role        string `json:"role"` // "producer" | "consumer" | "client" | "server" | "bidirectional"
	Description string `json:"description,omitempty"`
}

// ContractOperation describes an individual endpoint, RPC, subject, table, frame, or tool in a contract.
type ContractOperation struct {
	Name        string `json:"name"`
	Kind        string `json:"kind"` // "GET" | "POST" | "DELETE" | "RPC" | "BIDI_STREAM" | "SERVER_STREAM" | "PUB" | "SUB" | "TABLE" | "TOOL" | "FRAME" | "SSE"
	Target      string `json:"target"`
	Input       string `json:"input,omitempty"`
	Output      string `json:"output,omitempty"`
	Description string `json:"description,omitempty"`
}

// ExchangeContract represents a single exhaustive communication contract type for a microservice.
type ExchangeContract struct {
	ID           string              `json:"id"`
	Type         string              `json:"type"`
	TabLabel     string              `json:"tabLabel,omitempty"`
	Icon         string              `json:"icon,omitempty"`
	Direction    string              `json:"direction,omitempty"` // "inbound" | "outbound" | "bidirectional"
	Transport    string              `json:"transport,omitempty"`
	Address      string              `json:"address,omitempty"`
	Port         int                 `json:"port,omitempty"`
	Framing      string              `json:"framing,omitempty"`
	Auth         string              `json:"auth,omitempty"`
	Summary      string              `json:"summary,omitempty"`
	Source       string              `json:"source,omitempty"`
	Peers        []ContractPeer      `json:"peers,omitempty"`
	Operations   []ContractOperation `json:"operations,omitempty"`
	SchemaFormat string              `json:"schemaFormat,omitempty"` // "proto3" | "capnp" | "sql" | "json" | "wire" | "sse"
	Schema       string              `json:"schema,omitempty"`
}

// ContractsEnvelope is the standard HTTP response payload for GET /api/v1/contracts.
type ContractsEnvelope struct {
	Service     string             `json:"service"`
	Version     string             `json:"version,omitempty"`
	Reliable    bool               `json:"reliable"`
	Exhaustive  bool               `json:"exhaustive"`
	GeneratedAt string             `json:"generatedAt"`
	Source      string             `json:"source"`
	Contracts   []ExchangeContract `json:"contracts"`
}

// -----------------------------------------------------------------------------

// ResolveContractPort extracts the TCP/UDP port integer from a host:port string.
func ResolveContractPort(addr string) int {
	clean := strings.TrimSpace(addr)
	if clean == "" {
		return 0
	}
	if _, portStr, err := net.SplitHostPort(clean); err == nil {
		if port, convErr := strconv.Atoi(portStr); convErr == nil {
			return port
		}
	}
	if idx := strings.LastIndex(clean, ":"); idx >= 0 {
		if port, err := strconv.Atoi(clean[idx+1:]); err == nil {
			return port
		}
	}
	return 0
}

// DisplayAddress returns a client-friendly address string, falling back cleanly when unset.
func DisplayAddress(addr string) string {
	clean := strings.TrimSpace(addr)
	if clean == "" {
		return "dynamic"
	}
	if strings.HasPrefix(clean, ":") {
		return "127.0.0.1" + clean
	}
	if strings.HasPrefix(clean, "0.0.0.0:") {
		return "127.0.0.1:" + strings.TrimPrefix(clean, "0.0.0.0:")
	}
	return clean
}

// NewContractsEnvelope wraps microservice-owned contracts with UTC generation metadata.
func NewContractsEnvelope(service, version, source string, contracts []ExchangeContract) ContractsEnvelope {
	if contracts == nil {
		contracts = []ExchangeContract{}
	}
	if strings.TrimSpace(version) == "" {
		version = "0.0.1"
	}
	if strings.TrimSpace(source) == "" {
		source = fmt.Sprintf("%s runtime", service)
	}
	return ContractsEnvelope{
		Service:     service,
		Version:     version,
		Reliable:    true,
		Exhaustive:  true,
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
		Source:      source,
		Contracts:   contracts,
	}
}

// -----------------------------------------------------------------------------

var (
	protoPkgRE     = regexp.MustCompile(`(?m)^\s*package\s+([A-Za-z0-9_.]+)\s*;`)
	protoServiceRE = regexp.MustCompile(`(?s)service\s+([A-Za-z0-9_]+)\s*\{([^}]*)\}`)
	protoRPCRE     = regexp.MustCompile(`rpc\s+([A-Za-z0-9_]+)\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)\s+returns\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)`)
	capnpStructRE  = regexp.MustCompile(`(?s)struct\s+([A-Za-z0-9_]+)\s*\{([^}]*)\}`)
	capnpEnumRE    = regexp.MustCompile(`(?s)enum\s+([A-Za-z0-9_]+)\s*\{([^}]*)\}`)
)

// ExtractProtoTextOperations parses RPC declarations directly from an embedded .proto file.
func ExtractProtoTextOperations(protoText string) []ContractOperation {
	var ops []ContractOperation
	pkgPrefix := ""
	if m := protoPkgRE.FindStringSubmatch(protoText); len(m) == 2 {
		pkgPrefix = m[1] + "."
	}
	for _, svcMatch := range protoServiceRE.FindAllStringSubmatch(protoText, -1) {
		svcName := svcMatch[1]
		body := svcMatch[2]
		for _, rpcMatch := range protoRPCRE.FindAllStringSubmatch(body, -1) {
			rpcName := rpcMatch[1]
			inStream := strings.TrimSpace(rpcMatch[2]) != ""
			inType := rpcMatch[3]
			outStream := strings.TrimSpace(rpcMatch[4]) != ""
			outType := rpcMatch[5]
			kind := "RPC"
			if inStream && outStream {
				kind = "BIDI_STREAM"
			} else if outStream {
				kind = "SERVER_STREAM"
			} else if inStream {
				kind = "CLIENT_STREAM"
			}
			inPrefix := ""
			if inStream {
				inPrefix = "stream "
			}
			outPrefix := ""
			if outStream {
				outPrefix = "stream "
			}
			ops = append(ops, ContractOperation{
				Name:        rpcName,
				Kind:        kind,
				Target:      pkgPrefix + svcName + "/" + rpcName,
				Input:       inPrefix + inType,
				Output:      outPrefix + outType,
				Description: svcName + "." + rpcName,
			})
		}
	}
	return ops
}

// ExtractCapnpOperations extracts structs and enums directly from an embedded .capnp file.
func ExtractCapnpOperations(capnpText string) []ContractOperation {
	var ops []ContractOperation
	for _, em := range capnpEnumRE.FindAllStringSubmatch(capnpText, -1) {
		enumName := em[1]
		lines := compactNonCommentLines(em[2])
		ops = append(ops, ContractOperation{
			Name:        enumName,
			Kind:        "ENUM",
			Target:      "enum " + enumName,
			Output:      strings.Join(lines, ", "),
			Description: "Cap'n Proto enum definition",
		})
	}
	for _, sm := range capnpStructRE.FindAllStringSubmatch(capnpText, -1) {
		structName := sm[1]
		lines := compactNonCommentLines(sm[2])
		ops = append(ops, ContractOperation{
			Name:        structName,
			Kind:        "STRUCT",
			Target:      "struct " + structName,
			Input:       strings.Join(lines, "; "),
			Description: "Cap'n Proto wire struct definition",
		})
	}
	return ops
}

func compactNonCommentLines(block string) []string {
	var out []string
	for _, raw := range strings.Split(block, "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if idx := strings.Index(line, "#"); idx >= 0 {
			line = strings.TrimSpace(line[:idx])
		}
		if line != "" {
			out = append(out, strings.TrimSuffix(line, ";"))
		}
	}
	return out
}

// RenderProtoIDL reconstructs canonical proto3 source from a compiled protoreflect FileDescriptor.
func RenderProtoIDL(fd protoreflect.FileDescriptor) string {
	if fd == nil {
		return ""
	}
	var b strings.Builder
	b.WriteString("syntax = \"proto3\";\n")
	if pkg := string(fd.Package()); pkg != "" {
		b.WriteString(fmt.Sprintf("\npackage %s;\n", pkg))
	}
	services := fd.Services()
	for i := 0; i < services.Len(); i++ {
		svc := services.Get(i)
		b.WriteString(fmt.Sprintf("\nservice %s {\n", svc.Name()))
		methods := svc.Methods()
		for j := 0; j < methods.Len(); j++ {
			m := methods.Get(j)
			inStr, outStr := "", ""
			if m.IsStreamingClient() {
				inStr = "stream "
			}
			if m.IsStreamingServer() {
				outStr = "stream "
			}
			b.WriteString(fmt.Sprintf("  rpc %s (%s%s) returns (%s%s);\n", m.Name(), inStr, m.Input().Name(), outStr, m.Output().Name()))
		}
		b.WriteString("}\n")
	}
	topEnums := fd.Enums()
	for i := 0; i < topEnums.Len(); i++ {
		writeProtoEnum(&b, topEnums.Get(i), "")
	}
	msgs := fd.Messages()
	for i := 0; i < msgs.Len(); i++ {
		writeProtoMessage(&b, msgs.Get(i), "")
	}
	return strings.TrimSpace(b.String())
}

func writeProtoEnum(b *strings.Builder, en protoreflect.EnumDescriptor, indent string) {
	b.WriteString(fmt.Sprintf("\n%senum %s {\n", indent, en.Name()))
	vals := en.Values()
	for j := 0; j < vals.Len(); j++ {
		v := vals.Get(j)
		b.WriteString(fmt.Sprintf("%s  %s = %d;\n", indent, v.Name(), v.Number()))
	}
	b.WriteString(fmt.Sprintf("%s}\n", indent))
}

func writeProtoMessage(b *strings.Builder, msg protoreflect.MessageDescriptor, indent string) {
	b.WriteString(fmt.Sprintf("\n%smessage %s {\n", indent, msg.Name()))
	enums := msg.Enums()
	for i := 0; i < enums.Len(); i++ {
		writeProtoEnum(b, enums.Get(i), indent+"  ")
	}
	nested := msg.Messages()
	for i := 0; i < nested.Len(); i++ {
		if !nested.Get(i).IsMapEntry() {
			writeProtoMessage(b, nested.Get(i), indent+"  ")
		}
	}
	fields := msg.Fields()
	for i := 0; i < fields.Len(); i++ {
		f := fields.Get(i)
		prefix := ""
		if f.Cardinality() == protoreflect.Repeated {
			prefix = "repeated "
		}
		typeName := f.Kind().String()
		if f.Kind() == protoreflect.EnumKind && f.Enum() != nil {
			typeName = string(f.Enum().Name())
		} else if f.Kind() == protoreflect.MessageKind && f.Message() != nil {
			typeName = string(f.Message().Name())
		}
		b.WriteString(fmt.Sprintf("%s  %s%s %s = %d;\n", indent, prefix, typeName, f.Name(), f.Number()))
	}
	b.WriteString(fmt.Sprintf("%s}\n", indent))
}

