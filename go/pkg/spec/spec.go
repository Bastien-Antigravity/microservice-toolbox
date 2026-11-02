package spec

/*
ESSENTIAL PROCESS:
Standardizes self-describing microservice specifications and dynamic
registration with web-interface across the Bastien-Antigravity fleet.
Auto-resolves runtime listen/REST/gRPC addresses, dynamic semver, active
profile, and documentation links from AppConfig.

FAIL-FAST PRINCIPLE:
Zero silent fallbacks, zero default values, and zero dummy placeholders.
Microservices must explicitly declare their own specification metadata
(name, tag, layer, category, description, docLink, protocol, framing).
Configuration addresses (including web_interface) must resolve strictly;
missing capabilities, missing ports, or missing metadata FAIL FAST immediately.

DATA FLOW:
1. Microservice ServiceSpec + Capability Name -> Dynamic AppConfig Lookups
2. Strict Fail-Fast Validation of all required fields & dynamic endpoints
3. POST to /api/v1/register with exponential backoff and randomized jitter

KEY PARAMETERS:
- appConfig: Active AppConfig for capability host/port/version resolution.
- logger: Universal Logger for status logging and retry diagnostics.
- capability: Capability key in AppConfig e.g. "config_server".
- baseSpec: Microservice-provided ServiceSpec containing domain metadata.
*/

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"time"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	toolbox_lifecycle "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/lifecycle"
	unilog_interfaces "github.com/Bastien-Antigravity/universal-logger/src/interfaces"
)

// ProtocolSpec describes a single network protocol and port exposed by a service.
type ProtocolSpec struct {
	Type        string `json:"type"`        // "TCP", "REST", "gRPC", "WebSocket", "SSE", "SQL"
	Port        int    `json:"port"`        // Port number
	Framing     string `json:"framing"`     // e.g. "4-byte length prefix (safe-socket)", "HTTP/1.1 JSON", "Protobuf Stream"
	Description string `json:"description"`
}

// ServiceSpec is the canonical declarative specification of a microservice.
// Microservices must explicitly provide their own domain metadata; zero dummy defaults are permitted.
type ServiceSpec struct {
	Name          string                 `json:"name"`
	Tag           string                 `json:"tag"`
	URL           string                 `json:"url"`          // Dynamic if empty (from REST/ListenAddr)
	NavTitle      string                 `json:"navTitle"`     // Defaults to Name if empty
	Layer         string                 `json:"layer"`        // Required: "L1", "L2", "L3"
	Category      string                 `json:"category"`     // Required: "Base Fleet", "Domain Services", "Secure Controls"
	Priority      int                    `json:"priority"`     // Lower number = higher priority
	Icon          string                 `json:"icon"`         // FontAwesome icon class
	RequiresAuth  bool                   `json:"requiresAuth"`
	Capability    string                 `json:"capability"`   // Capability key in AppConfig e.g. "config_server"
	Description   string                 `json:"desc"`         // Required description
	Protocol      string                 `json:"protocol"`     // Required: e.g. "TCP / SafeSocket, REST & gRPC"
	Framing       string                 `json:"framing"`      // Required: e.g. "Port %s TCP / Port %s REST"
	DocLink       string                 `json:"docLink"`      // Required: Obsidian vault markdown path
	Protocols     []ProtocolSpec         `json:"protocols,omitempty"`
	DataStructure map[string]interface{} `json:"dataStructure,omitempty"`
	FlowDiagram   []string               `json:"flowDiagram,omitempty"`
	SDKLang       string                 `json:"sdkLang,omitempty"`
	SourceCode    string                 `json:"sourceCode,omitempty"`
}

// -----------------------------------------------------------------------------

func extractPort(addr string) string {
	if addr == "" {
		return ""
	}
	parts := strings.Split(addr, ":")
	if len(parts) >= 2 {
		return parts[len(parts)-1]
	}
	return addr
}

// -----------------------------------------------------------------------------

// BuildSpecFromConfig validates and enriches a ServiceSpec using dynamic parameters
// from AppConfig. ZERO SILENT FALLBACK: Fails fast immediately if any required field
// or capability address is missing.
func BuildSpecFromConfig(appConfig *toolbox_config.AppConfig, capability string, baseSpec ServiceSpec) (ServiceSpec, error) {
	// 1. Validate AppConfig strictly (FAIL-FAST)
	if appConfig == nil {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: appConfig is strictly required (nil provided) (FAIL-FAST)")
	}

	// 2. Validate Capability strictly (FAIL-FAST)
	capability = strings.TrimSpace(capability)
	if capability == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: capability name is strictly required (empty provided) (FAIL-FAST)")
	}

	s := baseSpec
	s.Capability = capability

	// 3. Validate Microservice-provided metadata (FAIL-FAST: ZERO DUMMY FALLBACKS)
	if strings.TrimSpace(s.Name) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Name' is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.Tag) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Tag' is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.Layer) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Layer' (L1|L2|L3) is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.Category) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Category' is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.Description) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Description' is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.DocLink) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'DocLink' is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.Protocol) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Protocol' is strictly required for capability %q (FAIL-FAST)", capability)
	}
	if strings.TrimSpace(s.Framing) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: 'Framing' is strictly required for capability %q (FAIL-FAST)", capability)
	}

	if s.NavTitle == "" {
		s.NavTitle = s.Name
	}

	// 4. Resolve URL and endpoints from AppConfig if not provided directly
	tcpAddr, _ := appConfig.GetListenAddr(capability)
	restAddr, _ := appConfig.GetRESTAddr(capability)
	grpcAddr, _ := appConfig.GetGRPCListenAddr(capability)

	tcpPort := extractPort(tcpAddr)
	restPort := extractPort(restAddr)
	grpcPort := extractPort(grpcAddr)

	if s.URL == "" {
		if restAddr != "" {
			s.URL = "http://" + restAddr
		} else if tcpAddr != "" {
			s.URL = "http://" + tcpAddr
		} else {
			return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: unable to resolve URL for capability %q from configuration (FAIL-FAST)", capability)
		}
	}

	// 5. Framing interpolation: If caller provided format string with %s, populate available ports
	if strings.Contains(s.Framing, "%s") {
		var available []interface{}
		for _, p := range []string{tcpPort, restPort, grpcPort} {
			if p != "" {
				available = append(available, p)
			}
		}
		count := strings.Count(s.Framing, "%s")
		if len(available) < count {
			return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: framing %q requires %d port(s), but only %d available for capability %q (FAIL-FAST)", s.Framing, count, len(available), capability)
		}
		switch count {
		case 3:
			s.Framing = fmt.Sprintf(s.Framing, available[0], available[1], available[2])
		case 2:
			s.Framing = fmt.Sprintf(s.Framing, available[0], available[1])
		case 1:
			s.Framing = fmt.Sprintf(s.Framing, available[0])
		}
	}

	// 6. Dynamic Semver Resolution (FAIL-FAST)
	ver := appConfig.GetVersion()
	if strings.TrimSpace(ver) == "" {
		return ServiceSpec{}, fmt.Errorf("spec.BuildSpecFromConfig: dynamic version resolution returned empty string (FAIL-FAST)")
	}

	// 7. Populate DataStructure dynamically
	if s.DataStructure == nil {
		s.DataStructure = make(map[string]interface{})
	}
	s.DataStructure["version"] = ver
	s.DataStructure["capability"] = capability
	ports := make(map[string]string)
	if tcpPort != "" {
		ports["tcp"] = tcpPort
	}
	if restPort != "" {
		ports["rest"] = restPort
	}
	if grpcPort != "" {
		ports["grpc"] = grpcPort
	}
	if len(ports) > 0 {
		s.DataStructure["ports"] = ports
	}
	if host, err := os.Hostname(); err == nil {
		s.DataStructure["node"] = host
	}

	return s, nil
}

// -----------------------------------------------------------------------------

// Publish validates service specification synchronously (FAIL-FAST) and publishes
// to web-interface in a non-blocking background goroutine with exponential backoff.
func Publish(appConfig *toolbox_config.AppConfig, logger unilog_interfaces.Logger, capability string, s ServiceSpec) error {
	// 1. Validate web-interface address synchronously (FAIL-FAST)
	if appConfig == nil {
		if logger != nil {
			logger.Critical("spec.Publish: appConfig is strictly required (nil provided) (FAIL-FAST)")
		}
		return fmt.Errorf("spec.Publish: appConfig is strictly required (nil provided) (FAIL-FAST)")
	}
	webAddr, err := appConfig.GetListenAddr("web_interface")
	if err != nil || strings.TrimSpace(webAddr) == "" {
		if logger != nil {
			logger.Critical("spec.Publish: Capability 'web_interface' is unresolvable from configuration: %v (FAIL-FAST)", err)
		}
		return fmt.Errorf("spec.Publish: capability 'web_interface' is unresolvable: %w (FAIL-FAST)", err)
	}

	// 2. Validate and enrich spec synchronously (FAIL-FAST)
	enriched, err := BuildSpecFromConfig(appConfig, capability, s)
	if err != nil {
		if logger != nil {
			logger.Critical("spec.Publish: Specification validation failed for %q: %v (FAIL-FAST)", capability, err)
		}
		return err
	}

	go func() {
		_ = PublishSync(context.Background(), appConfig, logger, capability, enriched)
	}()
	return nil
}

// -----------------------------------------------------------------------------

// PublishWithLifecycle binds dynamic spec publishing to the service's Lifecycle Manager,
// validating synchronously (FAIL-FAST) and registering the background worker context cancellation with lm.
func PublishWithLifecycle(appConfig *toolbox_config.AppConfig, logger unilog_interfaces.Logger, lm *toolbox_lifecycle.Manager, capability string, s ServiceSpec) error {
	// 1. Synchronous validation (FAIL-FAST)
	if appConfig == nil {
		if logger != nil {
			logger.Critical("spec.PublishWithLifecycle: appConfig is strictly required (nil provided) (FAIL-FAST)")
		}
		return fmt.Errorf("spec.PublishWithLifecycle: appConfig is strictly required (nil provided) (FAIL-FAST)")
	}
	webAddr, err := appConfig.GetListenAddr("web_interface")
	if err != nil || strings.TrimSpace(webAddr) == "" {
		if logger != nil {
			logger.Critical("spec.PublishWithLifecycle: Capability 'web_interface' is unresolvable from configuration: %v (FAIL-FAST)", err)
		}
		return fmt.Errorf("spec.PublishWithLifecycle: capability 'web_interface' is unresolvable: %w (FAIL-FAST)", err)
	}

	enriched, err := BuildSpecFromConfig(appConfig, capability, s)
	if err != nil {
		if logger != nil {
			logger.Critical("spec.PublishWithLifecycle: Specification validation failed for %q: %v (FAIL-FAST)", capability, err)
		}
		return err
	}

	ctx, cancel := context.WithCancel(context.Background())
	if lm != nil {
		lm.Register("OpenMFEPublisher_"+capability, func() error {
			cancel()
			return nil
		})
	}
	go func() {
		_ = PublishSync(ctx, appConfig, logger, capability, enriched)
	}()
	return nil
}

// -----------------------------------------------------------------------------

// PublishSync builds the dynamic spec from AppConfig and executes registration with web-interface
// with infinite retries and exponential backoff until success or context cancellation.
// FAIL-FAST: If appConfig is nil, web_interface is not resolvable, or spec validation fails,
// returns error immediately.
func PublishSync(ctx context.Context, appConfig *toolbox_config.AppConfig, logger unilog_interfaces.Logger, capability string, s ServiceSpec) error {
	// 1. Validate AppConfig strictly (FAIL-FAST)
	if appConfig == nil {
		if logger != nil {
			logger.Critical("spec.PublishSync: appConfig is strictly required (nil provided) (FAIL-FAST)")
		}
		return fmt.Errorf("spec.PublishSync: appConfig is strictly required (nil provided) (FAIL-FAST)")
	}

	// 2. Resolve web-interface address dynamically (FAIL-FAST, ZERO SILENT FALLBACK)
	webAddr, err := appConfig.GetListenAddr("web_interface")
	if err != nil || strings.TrimSpace(webAddr) == "" {
		if logger != nil {
			logger.Critical("spec.PublishSync: Capability 'web_interface' is unresolvable from configuration: %v (FAIL-FAST)", err)
		}
		return fmt.Errorf("spec.PublishSync: capability 'web_interface' is unresolvable: %w (FAIL-FAST)", err)
	}
	regURL := fmt.Sprintf("http://%s/api/v1/register", webAddr)

	// 3. Build & validate dynamic ServiceSpec from AppConfig (FAIL-FAST)
	enriched, err := BuildSpecFromConfig(appConfig, capability, s)
	if err != nil {
		if logger != nil {
			logger.Critical("spec.PublishSync: Failed to build spec for %q: %v (FAIL-FAST)", capability, err)
		}
		return err
	}

	// 4. Serialize payload
	payloadBytes, err := json.Marshal(enriched)
	if err != nil {
		if logger != nil {
			logger.Error("spec.PublishSync: Failed to serialize service spec for %s: %v", enriched.Name, err)
		}
		return err
	}

	client := &http.Client{Timeout: 3 * time.Second}
	delay := 500 * time.Millisecond
	maxDelay := 30 * time.Second

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodPost, regURL, bytes.NewBuffer(payloadBytes))
		if err == nil {
			req.Header.Set("Content-Type", "application/json")
			resp, err := client.Do(req)
			if err == nil {
				if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusCreated {
					resp.Body.Close()
					if logger != nil {
						logger.Info("spec.PublishSync: Service '%s' successfully published spec to %s", enriched.Name, regURL)
					}
					return nil
				}
				resp.Body.Close()
				if logger != nil {
					logger.Warning("spec.PublishSync: Registration for '%s' returned status %d. Retrying...", enriched.Name, resp.StatusCode)
				}
			} else {
				if logger != nil {
					logger.Debug("spec.PublishSync: Waiting for web-interface at %s (%v). Retrying in %v...", regURL, err, delay)
				}
			}
		}

		// Exponential backoff with randomized jitter
		jitter := time.Duration(rand.Int63n(int64(delay / 2)))
		sleepDuration := delay + jitter

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(sleepDuration):
		}

		delay *= 2
		if delay > maxDelay {
			delay = maxDelay
		}
	}
}
