package wiretap

// =============================================================================
// ESSENTIAL PROCESS:
// Provides a distinct, lock-free atomic switchable real-time transport telemetry
// wrapper ("WireTap") across safe-socket, gRPC, NATS, and HTTP/SSE connections.
// Aggregates inter-service connections and segregated information channels in
// memory with zero mutexes on the hot path, and periodically flushes snapshots
// to the web-interface topology hub.
//
// DATA FLOW:
// 1. Input: Transport wrappers (safe-socket hook, gRPC interceptors, NATS/HTTP wrappers).
// 2. Logic: Lock-free atomic.Bool check (`IsEnabled()`). When enabled, updates
//    lock-free sync.Map + atomic counters per (source, target, protocol) edge
//    and segregated channel (RPC method, NATS subject, safe-socket frame type).
// 3. Output: Snapshot []EdgeReport for local inspection and 2s debounced push
//    to web-interface (/api/v1/system/wiretap/ingest), syncing runtime toggle state.
//
// KEY PARAMETERS:
// - enabled: Lock-free atomic.Bool switch modifiable via config or runtime API.
// =============================================================================

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	safesocket "github.com/Bastien-Antigravity/safe-socket"
)

// ChannelMetric represents a single segregated information stream on an edge
// (e.g., a specific gRPC method, NATS subject, MCP tool, or safe-socket frame type).
type ChannelMetric struct {
	Channel     string  `json:"channel"`
	Category    string  `json:"category"`  // e.g. "rpc", "pubsub", "frame", "heartbeat", "sse", "external"
	Direction   string  `json:"direction"` // "outbound", "inbound", "bidirectional"
	Frames      uint64  `json:"frames"`
	Bytes       uint64  `json:"bytes"`
	Errors      uint64  `json:"errors"`
	AvgLatMs    float64 `json:"avg_latency_ms"`
	LastSeenIso string  `json:"last_seen"`
	LastPayload string  `json:"last_payload,omitempty"`
}

// EdgeReport represents a real-time observed connection between two ecosystem nodes
// along with all segregated information channels exchanged over that connection.
type EdgeReport struct {
	Source      string          `json:"source"`
	Target      string          `json:"target"`
	Protocol    string          `json:"protocol"` // "SAFESOCKET", "GRPC", "NATS", "HTTP", "SSE"
	Framing     string          `json:"framing"`
	ActiveConns int64           `json:"active_conns"`
	TotalFrames uint64          `json:"total_frames"`
	TotalBytes  uint64          `json:"total_bytes"`
	TotalErrors uint64          `json:"total_errors"`
	LastSeenIso string          `json:"last_seen"`
	IsExternal  bool            `json:"is_external"`
	Channels    []ChannelMetric `json:"channels"`
}

// IngestPayload is the wire format posted by microservices to web-interface.
type IngestPayload struct {
	Reporter  string       `json:"reporter"`
	Timestamp string       `json:"timestamp"`
	Enabled   bool         `json:"enabled"`
	Edges     []EdgeReport `json:"edges"`
}

// IngestResponse is returned by web-interface to synchronize the global toggle state.
type IngestResponse struct {
	Status  string `json:"status"`
	Enabled bool   `json:"enabled"`
}

// -----------------------------------------------------------------------------
// Lock-Free Internal State
// -----------------------------------------------------------------------------

type atomicChannelEntry struct {
	channel     string
	category    string
	direction   string
	frames      atomic.Uint64
	bytes       atomic.Uint64
	errors      atomic.Uint64
	totalLatUs  atomic.Uint64
	latSamples  atomic.Uint64
	lastSeenMs  atomic.Int64
	lastPayload atomic.Pointer[string]
}

type atomicEdgeEntry struct {
	source      string
	target      string
	protocol    string
	framing     atomic.Pointer[string]
	activeConns atomic.Int64
	totalFrames atomic.Uint64
	totalBytes  atomic.Uint64
	totalErrors atomic.Uint64
	lastSeenMs  atomic.Int64
	isExternal  atomic.Bool
	channels    sync.Map // string(channel) -> *atomicChannelEntry
}

var (
	// enabled is the lock-free atomic switch for the entire WireTap subsystem.
	enabled atomic.Bool

	// localService stores the canonical service ID of the current process.
	localService atomic.Pointer[string]

	// webHubURL stores the resolved http://host:port of web-interface.
	webHubURL atomic.Pointer[string]

	// edges stores observed edges keyed by "source|target|protocol" using lock-free reads.
	edges sync.Map

	// portServiceMap maps "port" -> canonical capability name for peer identification.
	portServiceMap sync.Map

	// reporterOnce ensures the background reporter goroutine starts at most once.
	reporterOnce sync.Once
)

func init() {
	defaultSvc := "unknown_service"
	localService.Store(&defaultSvc)
}

// -----------------------------------------------------------------------------
// Lock-Free Atomic Switch API
// -----------------------------------------------------------------------------

// SetEnabled atomically switches real-time connection tracking ON or OFF
// across both microservice-toolbox and the underlying safe-socket root library.
// Zero mutexes are used.
func SetEnabled(on bool) {
	enabled.Store(on)
	safesocket.SetTelemetryEnabled(on)
}

// IsEnabled atomically returns whether real-time connection tracking is active.
// Zero mutexes are used.
func IsEnabled() bool {
	return enabled.Load()
}

// SetLocalService atomically sets the canonical service identifier for this process.
func SetLocalService(serviceName string) {
	normalized := NormalizeServiceID(serviceName)
	localService.Store(&normalized)
}

// GetLocalService atomically reads the canonical service identifier for this process.
func GetLocalService() string {
	if p := localService.Load(); p != nil && *p != "" {
		return *p
	}
	return "unknown_service"
}

// -----------------------------------------------------------------------------
// Configuration & Safe-Socket Bridge Initialization
// -----------------------------------------------------------------------------

// ConfigureFromConfig initializes WireTap from validated AppConfig, registers the lock-free
// safe-socket telemetry hook, populates the port-to-service lookup table from capabilities,
// and starts the background reporter loop.
func ConfigureFromConfig(serviceName string, appConfig *config.AppConfig) {
	SetLocalService(serviceName)

	rawEnabled := appConfig.GetLocalString("wiretap_enabled")
	if rawEnabled == "" {
		rawEnabled = appConfig.Get("common", "wiretap_enabled")
	}
	initialEnabled := rawEnabled == "" || strings.EqualFold(rawEnabled, "true")

	for capName := range appConfig.Config.Capabilities {
		normCap := NormalizeServiceID(capName)
		if addr, err := appConfig.GetListenAddr(capName); err == nil {
			registerAddrPort(addr, normCap)
		}
		if addr, err := appConfig.GetGRPCListenAddr(capName); err == nil {
			registerAddrPort(addr, normCap)
		}
		if addr, err := appConfig.GetRESTAddr(capName); err == nil {
			registerAddrPort(addr, normCap)
		}
	}

	if webAddr, err := appConfig.GetListenAddr("web_interface"); err == nil && webAddr != "" {
		url := "http://" + webAddr
		webHubURL.Store(&url)
	}

	safesocket.SetTelemetryHook(handleSafeSocketEvent)
	SetEnabled(initialEnabled)

	if GetLocalService() != "web_interface" {
		reporterOnce.Do(func() {
			go reporterLoop()
		})
	}
}

func handleSafeSocketEvent(ev safesocket.TelemetryEvent) {
	if !enabled.Load() {
		return
	}

	self := GetLocalService()
	peer := NormalizeServiceID(ev.PeerName)
	if peer == "" || peer == "unknown" || peer == "unknown_service" {
		peer = ResolveServiceByAddr(ev.RemoteAddr)
	}
	if peer == "" || peer == "unknown_service" {
		// If we are client dialing a known local port, RemoteAddr has the server port.
		// If we are server accepting a connection, LocalAddr has our server port.
		if ev.Role == "server" {
			peer = "safesocket_client"
		} else {
			peer = ResolveServiceByAddr(ev.LocalAddr)
		}
	}
	if peer == "" || peer == self {
		return
	}

	source := self
	target := peer
	direction := "outbound"
	if ev.Role == "server" {
		source = peer
		target = self
		direction = "inbound"
	}

	category := "frame"
	if strings.HasSuffix(ev.Channel, ":heartbeat") {
		category = "heartbeat"
	} else if strings.HasSuffix(ev.Channel, ":lifecycle") {
		category = "lifecycle"
	}

	framing := fmt.Sprintf("SafeSocket/%s (%s)", strings.ToUpper(ev.Transport), ev.ProfileName)
	connDelta := int64(0)
	if ev.EventType == safesocket.TelemetryEventConnect || ev.EventType == safesocket.TelemetryEventAccept {
		connDelta = 1
	} else if ev.EventType == safesocket.TelemetryEventDisconnect {
		connDelta = -1
	}

	RecordEventWithConnDelta(
		source,
		target,
		"SAFESOCKET",
		framing,
		ev.Channel,
		category,
		direction,
		string(ev.EventType),
		ev.Bytes,
		0,
		ev.HasError,
		false,
		connDelta,
	)
}

// -----------------------------------------------------------------------------
// Lock-Free Hot-Path Event Recording
// -----------------------------------------------------------------------------

// RecordEvent records a transport interaction and its segregated channel metrics
// if and only if the atomic switch is enabled.
func RecordEvent(
	source string,
	target string,
	protocol string,
	framing string,
	channel string,
	category string,
	direction string,
	payloadSummary string,
	bytesCount int,
	latencyMs float64,
	isErr bool,
	isExternal bool,
) {
	RecordEventWithConnDelta(
		source,
		target,
		protocol,
		framing,
		channel,
		category,
		direction,
		payloadSummary,
		bytesCount,
		latencyMs,
		isErr,
		isExternal,
		0,
	)
}

// RecordEventWithConnDelta records an event and atomically adjusts the active connection counter.
func RecordEventWithConnDelta(
	source string,
	target string,
	protocol string,
	framing string,
	channel string,
	category string,
	direction string,
	payloadSummary string,
	bytesCount int,
	latencyMs float64,
	isErr bool,
	isExternal bool,
	connDelta int64,
) {
	if !enabled.Load() {
		return
	}

	srcNorm := NormalizeServiceID(source)
	tgtNorm := NormalizeServiceID(target)
	if srcNorm == "" || tgtNorm == "" {
		return
	}
	protoUpper := strings.ToUpper(strings.TrimSpace(protocol))
	if protoUpper == "" {
		protoUpper = "TCP"
	}
	if channel == "" {
		channel = strings.ToLower(protoUpper) + ":default"
	}
	if category == "" {
		category = "data"
	}
	if direction == "" {
		direction = "outbound"
	}

	edgeKey := srcNorm + "|" + tgtNorm + "|" + protoUpper
	nowMs := time.Now().UnixMilli()

	var edge *atomicEdgeEntry
	if val, ok := edges.Load(edgeKey); ok {
		edge = val.(*atomicEdgeEntry)
	} else {
		newEdge := &atomicEdgeEntry{
			source:   srcNorm,
			target:   tgtNorm,
			protocol: protoUpper,
		}
		if framing != "" {
			fCopy := framing
			newEdge.framing.Store(&fCopy)
		}
		actual, _ := edges.LoadOrStore(edgeKey, newEdge)
		edge = actual.(*atomicEdgeEntry)
	}

	if framing != "" {
		fCopy := framing
		edge.framing.Store(&fCopy)
	}
	if isExternal {
		edge.isExternal.Store(true)
	}
	if connDelta != 0 {
		newCount := edge.activeConns.Add(connDelta)
		if newCount < 0 {
			edge.activeConns.Store(0)
		}
	} else if edge.activeConns.Load() == 0 {
		edge.activeConns.Store(1)
	}

	edge.totalFrames.Add(1)
	if bytesCount > 0 {
		edge.totalBytes.Add(uint64(bytesCount))
	}
	if isErr {
		edge.totalErrors.Add(1)
	}
	edge.lastSeenMs.Store(nowMs)

	// Segregated channel entry update (lock-free)
	var chEntry *atomicChannelEntry
	if cVal, ok := edge.channels.Load(channel); ok {
		chEntry = cVal.(*atomicChannelEntry)
	} else {
		newCh := &atomicChannelEntry{
			channel:   channel,
			category:  category,
			direction: direction,
		}
		actualCh, _ := edge.channels.LoadOrStore(channel, newCh)
		chEntry = actualCh.(*atomicChannelEntry)
	}

	chEntry.frames.Add(1)
	if bytesCount > 0 {
		chEntry.bytes.Add(uint64(bytesCount))
	}
	if isErr {
		chEntry.errors.Add(1)
	}
	if latencyMs > 0 {
		chEntry.totalLatUs.Add(uint64(latencyMs * 1000.0))
		chEntry.latSamples.Add(1)
	}
	chEntry.lastSeenMs.Store(nowMs)
	if payloadSummary != "" {
		pCopy := payloadSummary
		chEntry.lastPayload.Store(&pCopy)
	}
}

// -----------------------------------------------------------------------------
// Snapshot & Ingestion Merge
// -----------------------------------------------------------------------------

// Snapshot returns a point-in-time slice of all observed EdgeReports and their
// segregated channels.
func Snapshot() []EdgeReport {
	var reports []EdgeReport

	edges.Range(func(_, value any) bool {
		edge := value.(*atomicEdgeEntry)
		framing := ""
		if fp := edge.framing.Load(); fp != nil {
			framing = *fp
		}

		var chList []ChannelMetric
		edge.channels.Range(func(_, cVal any) bool {
			ce := cVal.(*atomicChannelEntry)
			avgLat := 0.0
			if samples := ce.latSamples.Load(); samples > 0 {
				avgLat = float64(ce.totalLatUs.Load()) / (1000.0 * float64(samples))
			}
			lastPayload := ""
			if lp := ce.lastPayload.Load(); lp != nil {
				lastPayload = *lp
			}
			lastSeen := ""
			if ms := ce.lastSeenMs.Load(); ms > 0 {
				lastSeen = time.UnixMilli(ms).UTC().Format(time.RFC3339)
			}
			chList = append(chList, ChannelMetric{
				Channel:     ce.channel,
				Category:    ce.category,
				Direction:   ce.direction,
				Frames:      ce.frames.Load(),
				Bytes:       ce.bytes.Load(),
				Errors:      ce.errors.Load(),
				AvgLatMs:    avgLat,
				LastSeenIso: lastSeen,
				LastPayload: lastPayload,
			})
			return true
		})

		sort.Slice(chList, func(i, j int) bool {
			return chList[i].Channel < chList[j].Channel
		})

		lastSeenEdge := ""
		if ms := edge.lastSeenMs.Load(); ms > 0 {
			lastSeenEdge = time.UnixMilli(ms).UTC().Format(time.RFC3339)
		}

		reports = append(reports, EdgeReport{
			Source:      edge.source,
			Target:      edge.target,
			Protocol:    edge.protocol,
			Framing:     framing,
			ActiveConns: edge.activeConns.Load(),
			TotalFrames: edge.totalFrames.Load(),
			TotalBytes:  edge.totalBytes.Load(),
			TotalErrors: edge.totalErrors.Load(),
			LastSeenIso: lastSeenEdge,
			IsExternal:  edge.isExternal.Load(),
			Channels:    chList,
		})
		return true
	})

	sort.Slice(reports, func(i, j int) bool {
		if reports[i].Source != reports[j].Source {
			return reports[i].Source < reports[j].Source
		}
		if reports[i].Target != reports[j].Target {
			return reports[i].Target < reports[j].Target
		}
		return reports[i].Protocol < reports[j].Protocol
	})

	return reports
}

// MergeRemoteSnapshot merges an EdgeReport batch pushed from a remote microservice
// into the local WireTap hub store (used by web-interface).
func MergeRemoteSnapshot(incoming []EdgeReport) {
	if !enabled.Load() {
		return
	}
	nowMs := time.Now().UnixMilli()

	for _, rep := range incoming {
		srcNorm := NormalizeServiceID(rep.Source)
		tgtNorm := NormalizeServiceID(rep.Target)
		protoUpper := strings.ToUpper(strings.TrimSpace(rep.Protocol))
		if srcNorm == "" || tgtNorm == "" || protoUpper == "" {
			continue
		}

		edgeKey := srcNorm + "|" + tgtNorm + "|" + protoUpper
		var edge *atomicEdgeEntry
		if val, ok := edges.Load(edgeKey); ok {
			edge = val.(*atomicEdgeEntry)
		} else {
			newEdge := &atomicEdgeEntry{
				source:   srcNorm,
				target:   tgtNorm,
				protocol: protoUpper,
			}
			actual, _ := edges.LoadOrStore(edgeKey, newEdge)
			edge = actual.(*atomicEdgeEntry)
		}

		if rep.Framing != "" {
			fCopy := rep.Framing
			edge.framing.Store(&fCopy)
		}
		if rep.IsExternal {
			edge.isExternal.Store(true)
		}
		if rep.ActiveConns > 0 {
			edge.activeConns.Store(rep.ActiveConns)
		}
		if rep.TotalFrames > edge.totalFrames.Load() {
			edge.totalFrames.Store(rep.TotalFrames)
		}
		if rep.TotalBytes >= edge.totalBytes.Load() {
			edge.totalBytes.Store(rep.TotalBytes)
		}
		edge.totalErrors.Store(rep.TotalErrors)
		edge.lastSeenMs.Store(nowMs)

		for _, ch := range rep.Channels {
			if ch.Channel == "" {
				continue
			}
			var chEntry *atomicChannelEntry
			if cVal, ok := edge.channels.Load(ch.Channel); ok {
				chEntry = cVal.(*atomicChannelEntry)
			} else {
				newCh := &atomicChannelEntry{
					channel:   ch.Channel,
					category:  ch.Category,
					direction: ch.Direction,
				}
				actualCh, _ := edge.channels.LoadOrStore(ch.Channel, newCh)
				chEntry = actualCh.(*atomicChannelEntry)
			}
			if ch.Frames >= chEntry.frames.Load() {
				chEntry.frames.Store(ch.Frames)
			}
			if ch.Bytes >= chEntry.bytes.Load() {
				chEntry.bytes.Store(ch.Bytes)
			}
			chEntry.errors.Store(ch.Errors)
			if ch.AvgLatMs > 0 {
				chEntry.totalLatUs.Store(uint64(ch.AvgLatMs * 1000.0))
				chEntry.latSamples.Store(1)
			}
			chEntry.lastSeenMs.Store(nowMs)
			if ch.LastPayload != "" {
				pCopy := ch.LastPayload
				chEntry.lastPayload.Store(&pCopy)
			}
		}
	}
}

// Reset clears all accumulated edges and channels (useful for tests or manual reset).
func Reset() {
	edges.Range(func(key, _ any) bool {
		edges.Delete(key)
		return true
	})
}

// -----------------------------------------------------------------------------
// Background Reporter to Web-Interface Hub
// -----------------------------------------------------------------------------

func reporterLoop() {
	client := &http.Client{Timeout: 1500 * time.Millisecond}
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		hubPtr := webHubURL.Load()
		if hubPtr == nil || *hubPtr == "" {
			continue
		}

		// Even when disabled locally, poll/ping lightly so if the user re-enables WireTap
		// from the web-interface toolbar, this microservice picks up `enabled: true`.
		var currentEdges []EdgeReport
		if enabled.Load() {
			currentEdges = Snapshot()
		}

		payload := IngestPayload{
			Reporter:  GetLocalService(),
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Enabled:   enabled.Load(),
			Edges:     currentEdges,
		}

		body, err := json.Marshal(payload)
		if err != nil {
			continue
		}

		resp, err := client.Post(*hubPtr+"/api/v1/system/wiretap/ingest", "application/json", bytes.NewReader(body))
		if err != nil {
			continue
		}

		var ingestResp IngestResponse
		if err := json.NewDecoder(resp.Body).Decode(&ingestResp); err == nil && ingestResp.Status != "" {
			if ingestResp.Enabled != enabled.Load() {
				SetEnabled(ingestResp.Enabled)
			}
		}
		_ = resp.Body.Close()
	}
}

// -----------------------------------------------------------------------------
// Address & Service Name Normalization Helpers
// -----------------------------------------------------------------------------

// NormalizeServiceID converts arbitrary service/component names into canonical mesh IDs.
func NormalizeServiceID(raw string) string {
	s := strings.TrimSpace(strings.ToLower(raw))
	s = strings.ReplaceAll(s, "-", "_")
	switch s {
	case "09_rag_engine", "rag_service", "obsidian_rag":
		return "rag_engine"
	case "08_squad_agent", "squad_agent":
		return "agent_squad"
	case "nats_server", "nats_broker":
		return "nats"
	case "postgres", "postgresql", "timescaledb":
		return "timescale_db"
	case "vector_db":
		return "chromadb"
	}
	return s
}

// ResolveServiceByAddr inspects a "host:port" address and resolves the canonical service ID.
func ResolveServiceByAddr(addr string) string {
	_, port := splitHostPortSafe(addr)
	if port == "" {
		return ""
	}
	if val, ok := portServiceMap.Load(port); ok {
		return val.(string)
	}
	return ""
}

func registerAddrPort(addr string, serviceID string) {
	_, port := splitHostPortSafe(addr)
	if port != "" && serviceID != "" {
		portServiceMap.Store(port, serviceID)
	}
}

func splitHostPortSafe(addr string) (string, string) {
	addr = strings.TrimSpace(addr)
	if addr == "" {
		return "", ""
	}
	if h, p, err := net.SplitHostPort(addr); err == nil {
		return h, p
	}
	if idx := strings.LastIndex(addr, ":"); idx != -1 {
		portCandidate := addr[idx+1:]
		if _, err := strconv.Atoi(portCandidate); err == nil {
			return addr[:idx], portCandidate
		}
	}
	return addr, ""
}
