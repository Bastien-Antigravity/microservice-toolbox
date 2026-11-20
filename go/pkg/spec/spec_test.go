package spec

/*
ESSENTIAL PROCESS:
Unit testing for declarative ServiceSpec dynamic validation, port extraction,
zero-fallback fail-fast verification, and resilient HTTP publishing.

DATA FLOW:
1. Valid ServiceSpec + AppConfig -> BuildSpecFromConfig -> Verify derived fields
2. Missing metadata fields -> BuildSpecFromConfig -> Verify immediate fail-fast error
3. Missing web_interface -> PublishSync -> Verify immediate fail-fast error
4. Mock HTTP Server -> PublishSync -> Verify payload delivery

KEY PARAMETERS:
- None (Unit Test Suite).
*/

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
)

// -----------------------------------------------------------------------------

func TestBuildSpecFromConfigValid(t *testing.T) {
	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil {
		t.Fatalf("Failed to load standalone config: %v", err)
	}

	if appConfig.Capabilities == nil {
		appConfig.Capabilities = make(map[string]interface{})
	}
	appConfig.Capabilities["config_server"] = map[string]interface{}{
		"ip":        "127.0.0.1",
		"port":      13306,
		"grpc_port": 13307,
		"rest_port": 13308,
	}

	base := ServiceSpec{
		Name:        "Config Server",
		Tag:         "config-server-mfe",
		Layer:       "L1",
		Category:    "Base Fleet",
		Priority:    20,
		Icon:        "fa-cogs",
		Description: "Centralized configuration repository and real-time distributor.",
		Protocol:    "TCP, REST & gRPC",
		Framing:     "Port %s TCP / Port %s REST / Port %s gRPC",
		DocLink:     "obsidian-brain/06-Microservices/Config-Server-Hub.md",
	}

	spec, err := BuildSpecFromConfig(appConfig, "config_server", base)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}

	if spec.Name != "Config Server" {
		t.Errorf("Expected Name 'Config Server', got %q", spec.Name)
	}
	if !strings.Contains(spec.Framing, "13306") || !strings.Contains(spec.Framing, "13308") || !strings.Contains(spec.Framing, "13307") {
		t.Errorf("Expected dynamic ports 13306, 13308, 13307 in framing: %s", spec.Framing)
	}
	if spec.DocLink != "obsidian-brain/06-Microservices/Config-Server-Hub.md" {
		t.Errorf("Expected DocLink 'obsidian-brain/06-Microservices/Config-Server-Hub.md', got %q", spec.DocLink)
	}
	if spec.DataStructure == nil || spec.DataStructure["version"] == nil {
		t.Errorf("Expected dynamic version in DataStructure: %v", spec.DataStructure)
	}
	if spec.URL != "http://127.0.0.1:13308" {
		t.Errorf("Expected dynamic REST URL 'http://127.0.0.1:13308', got %q", spec.URL)
	}
}

// -----------------------------------------------------------------------------

func TestBuildSpecFromConfig_EnhancedMetadata(t *testing.T) {
	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil {
		t.Fatalf("Failed to load standalone config: %v", err)
	}

	base := ServiceSpec{
		Name:        "Payment Gateway",
		Tag:         "payment-gateway-mfe",
		Layer:       "L2",
		Category:    "Domain Services",
		Description: "Handles payments.",
		Protocol:    "REST",
		Framing:     "Port %s REST",
		DocLink:     "obsidian-brain/06-Microservices/Payment-Gateway.md",
		Color:       "#38bdf8",
		Dependencies: []DependencySpec{
			{Target: "notif_server", Protocol: "grpc", Label: "Payment Alerts"},
			{Target: "timescale_db", Protocol: "sql", Label: "Transaction Ledger"},
		},
		Canvas: CanvasSpec{
			Icon:          "fa-credit-card",
			PreferredSlot: "domain",
		},
	}

	spec, err := BuildSpecFromConfig(appConfig, "config_server", base)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}

	if spec.NavRoute != "/mfe/Payment Gateway" {
		t.Errorf("Expected default NavRoute '/mfe/Payment Gateway', got %q", spec.NavRoute)
	}
	if spec.Canvas.Color != "#38bdf8" {
		t.Errorf("Expected Canvas.Color '#38bdf8', got %q", spec.Canvas.Color)
	}
	if spec.Health.ProbeType != "tcp" {
		t.Errorf("Expected default Health.ProbeType 'tcp', got %q", spec.Health.ProbeType)
	}
	if spec.Health.TimeoutMs != 350 {
		t.Errorf("Expected default Health.TimeoutMs 350, got %d", spec.Health.TimeoutMs)
	}
	if len(spec.Dependencies) != 2 {
		t.Errorf("Expected 2 dependencies, got %d", len(spec.Dependencies))
	}
}

// -----------------------------------------------------------------------------

func TestBuildSpecFromConfigFailFast(t *testing.T) {
	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil {
		t.Fatalf("Failed to load standalone config: %v", err)
	}

	validBase := ServiceSpec{
		Name:        "Config Server",
		Tag:         "config-server-mfe",
		Layer:       "L1",
		Category:    "Base Fleet",
		Description: "Centralized configuration repository.",
		Protocol:    "TCP",
		Framing:     "Port %s TCP",
		DocLink:     "obsidian-brain/06-Microservices/Config-Server-Hub.md",
	}

	// 1. Nil appConfig
	if _, err := BuildSpecFromConfig(nil, "config_server", validBase); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on nil appConfig")
	}

	// 2. Empty capability
	if _, err := BuildSpecFromConfig(appConfig, "", validBase); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on empty capability")
	}

	// 3. Missing Name
	missingName := validBase
	missingName.Name = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingName); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing Name")
	}

	// 4. Missing Layer
	missingLayer := validBase
	missingLayer.Layer = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingLayer); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing Layer")
	}

	// 5. Missing Category
	missingCategory := validBase
	missingCategory.Category = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingCategory); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing Category")
	}

	// 6. Missing Description
	missingDesc := validBase
	missingDesc.Description = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingDesc); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing Description")
	}

	// 7. Missing DocLink
	missingDoc := validBase
	missingDoc.DocLink = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingDoc); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing DocLink")
	}

	// 8. Missing Protocol
	missingProto := validBase
	missingProto.Protocol = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingProto); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing Protocol")
	}

	// 9. Missing Framing
	missingFraming := validBase
	missingFraming.Framing = ""
	if _, err := BuildSpecFromConfig(appConfig, "config_server", missingFraming); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on missing Framing")
	}

	// 10. Capability with no addresses in config
	if _, err := BuildSpecFromConfig(appConfig, "non_existent_capability", validBase); err == nil {
		t.Errorf("BuildSpecFromConfig must fail fast on non-existent capability")
	}
}

// -----------------------------------------------------------------------------

func TestPublishSyncFailFast(t *testing.T) {
	validBase := ServiceSpec{
		Name:        "Config Server",
		Tag:         "config-server-mfe",
		Layer:       "L1",
		Category:    "Base Fleet",
		Description: "Centralized config repository.",
		Protocol:    "TCP",
		Framing:     "Port %s TCP",
		DocLink:     "obsidian-brain/06-Microservices/Config-Server-Hub.md",
	}

	// 1. appConfig is nil
	err := PublishSync(context.Background(), nil, nil, "config_server", validBase)
	if err == nil {
		t.Errorf("PublishSync must FAIL FAST when appConfig is nil")
	}

	// 2. web_interface capability missing
	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil || appConfig == nil {
		appConfig = &toolbox_config.AppConfig{}
	}
	if appConfig.Capabilities == nil {
		appConfig.Capabilities = make(map[string]interface{})
	}
	appConfig.Capabilities["config_server"] = map[string]interface{}{"ip": "127.0.0.1", "port": 3306}
	delete(appConfig.Capabilities, "web_interface")

	err = PublishSync(context.Background(), appConfig, nil, "config_server", validBase)
	if err == nil {
		t.Errorf("PublishSync must FAIL FAST when web_interface is missing from configuration")
	} else if !strings.Contains(err.Error(), "web_interface") {
		t.Errorf("Error must mention web_interface: %v", err)
	}
}

// -----------------------------------------------------------------------------

func TestServiceSpecPublishSync(t *testing.T) {
	received := false
	var receivedPayload ServiceSpec

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/register" {
			t.Errorf("Unexpected path: %s", r.URL.Path)
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodPost {
			t.Errorf("Unexpected method: %s", r.Method)
			http.Error(w, "invalid method", http.StatusMethodNotAllowed)
			return
		}
		if err := json.NewDecoder(r.Body).Decode(&receivedPayload); err != nil {
			t.Errorf("Failed to decode payload: %v", err)
			http.Error(w, "bad json", http.StatusBadRequest)
			return
		}
		received = true
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte(`{"message":"registered"}`))
	}))
	defer ts.Close()

	serverAddr := strings.TrimPrefix(ts.URL, "http://")
	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil || appConfig == nil {
		appConfig = &toolbox_config.AppConfig{}
	}
	parts := strings.Split(serverAddr, ":")
	portNum := 0
	if len(parts) == 2 {
		portNum, _ = strconv.Atoi(parts[1])
	}
	appConfig.Set(map[string]map[string]string{
		"web_interface": {
			"ip":   parts[0],
			"port": strconv.Itoa(portNum),
		},
		"config_server": {
			"ip":   "127.0.0.1",
			"port": "3306",
		},
	})

	validBase := ServiceSpec{
		Name:        "Config Server",
		Tag:         "config-server-mfe",
		Layer:       "L1",
		Category:    "Base Fleet",
		Description: "Centralized config repository.",
		Protocol:    "TCP",
		Framing:     "Port %s TCP",
		DocLink:     "obsidian-brain/06-Microservices/Config-Server-Hub.md",
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	err = PublishSync(ctx, appConfig, nil, "config_server", validBase)
	if err != nil {
		t.Fatalf("PublishSync failed: %v", err)
	}

	if !received {
		t.Errorf("Server did not receive registration")
	}
	if receivedPayload.Name != "Config Server" {
		t.Errorf("Expected Name 'Config Server', got %q", receivedPayload.Name)
	}
	if receivedPayload.Capability != "config_server" {
		t.Errorf("Expected Capability 'config_server', got %q", receivedPayload.Capability)
	}
}

// -----------------------------------------------------------------------------

func TestBuildSpecFromConfig_BrainIDResolution(t *testing.T) {
	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil {
		t.Fatalf("Failed to load standalone config: %v", err)
	}
	if appConfig.Capabilities == nil {
		appConfig.Capabilities = make(map[string]interface{})
	}
	delete(appConfig.Capabilities, "squad_agent")
	delete(appConfig.Capabilities, "watchdog_agent")
	appConfig.Capabilities["config_server"] = map[string]interface{}{
		"ip":   "127.0.0.1",
		"port": 13306,
	}

	validBase := ServiceSpec{
		Name:        "Config Server",
		Tag:         "config-server-mfe",
		Layer:       "L1",
		Category:    "Base Fleet",
		Description: "Centralized configuration repository.",
		Protocol:    "TCP",
		Framing:     "Port %s TCP",
		DocLink:     "obsidian-brain/06-Microservices/Config-Server-Hub.md",
	}

	// 1. Omitted when neither struct, config capability, nor env is set
	t.Setenv("BRAIN_ID", "")
	t.Setenv("TARGET_BRAIN_ID", "")
	specEmpty, err := BuildSpecFromConfig(appConfig, "config_server", validBase)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if specEmpty.BrainID != "" {
		t.Errorf("Expected empty BrainID, got %q", specEmpty.BrainID)
	}
	rawEmpty, err := json.Marshal(specEmpty)
	if err != nil {
		t.Fatalf("json.Marshal failed: %v", err)
	}
	if strings.Contains(string(rawEmpty), `"brain_id"`) {
		t.Errorf("Expected brain_id to be omitted from JSON when empty, got %s", string(rawEmpty))
	}

	// 2. Falls back to TARGET_BRAIN_ID when BRAIN_ID and capabilities are unset
	t.Setenv("TARGET_BRAIN_ID", "brain-target")
	specTarget, err := BuildSpecFromConfig(appConfig, "config_server", validBase)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if specTarget.BrainID != "brain-target" {
		t.Errorf("Expected BrainID 'brain-target' from TARGET_BRAIN_ID, got %q", specTarget.BrainID)
	}

	// 3. BRAIN_ID takes precedence over TARGET_BRAIN_ID
	t.Setenv("BRAIN_ID", "brain-primary")
	specPrimary, err := BuildSpecFromConfig(appConfig, "config_server", validBase)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if specPrimary.BrainID != "brain-primary" {
		t.Errorf("Expected BrainID 'brain-primary' from BRAIN_ID, got %q", specPrimary.BrainID)
	}
	rawPrimary, err := json.Marshal(specPrimary)
	if err != nil {
		t.Fatalf("json.Marshal failed: %v", err)
	}
	if !strings.Contains(string(rawPrimary), `"brain_id":"brain-primary"`) {
		t.Errorf("Expected brain_id in JSON payload, got %s", string(rawPrimary))
	}

	// 4. watchdog_agent.brain_id takes precedence over BRAIN_ID and TARGET_BRAIN_ID
	appConfig.Capabilities["watchdog_agent"] = map[string]interface{}{
		"brain_id": "watchdog-brain",
	}
	specWatchdog, err := BuildSpecFromConfig(appConfig, "config_server", validBase)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if specWatchdog.BrainID != "watchdog-brain" {
		t.Errorf("Expected BrainID 'watchdog-brain' from watchdog_agent.brain_id, got %q", specWatchdog.BrainID)
	}

	// 5. squad_agent.target_brain_id takes precedence over watchdog_agent.brain_id and env vars
	appConfig.Capabilities["squad_agent"] = map[string]interface{}{
		"target_brain_id": "squad-brain",
	}
	specSquad, err := BuildSpecFromConfig(appConfig, "config_server", validBase)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if specSquad.BrainID != "squad-brain" {
		t.Errorf("Expected BrainID 'squad-brain' from squad_agent.target_brain_id, got %q", specSquad.BrainID)
	}

	// 6. Explicit struct BrainID overrides config capabilities and env vars
	explicitBase := validBase
	explicitBase.BrainID = "brain-explicit"
	specExplicit, err := BuildSpecFromConfig(appConfig, "config_server", explicitBase)
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if specExplicit.BrainID != "brain-explicit" {
		t.Errorf("Expected explicit BrainID 'brain-explicit', got %q", specExplicit.BrainID)
	}
}

// -----------------------------------------------------------------------------

func TestBuildSpecFromConfig_StandaloneYAMLBrainIDZeroEnv(t *testing.T) {
	tmpDir := t.TempDir()
	yamlPath := filepath.Join(tmpDir, "standalone.yaml")
	yamlContent := `common:
  name: order_router
capabilities:
  order_router:
    ip: 127.0.0.1
    port: 14100
  squad_agent:
    target_brain_id: "trading-brain"
`
	if err := os.WriteFile(yamlPath, []byte(yamlContent), 0644); err != nil {
		t.Fatalf("Failed to write standalone.yaml: %v", err)
	}

	t.Setenv("CONFIG_PATH", yamlPath)
	t.Setenv("SHARED_CONFIG_PATH", "")
	t.Setenv("BRAIN_ID", "")
	t.Setenv("TARGET_BRAIN_ID", "")

	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil {
		t.Fatalf("LoadConfig(standalone) failed: %v", err)
	}

	spec, err := BuildSpecFromConfig(appConfig, "order_router", ServiceSpec{
		Name:        "Order Router",
		Tag:         "order-router-mfe",
		Layer:       "L3",
		Category:    "Domain Services",
		Description: "Routes trading orders.",
		Protocol:    "TCP",
		Framing:     "Port %s TCP",
		DocLink:     "obsidian-brain/06-Microservices/Order-Router.md",
	})
	if err != nil {
		t.Fatalf("BuildSpecFromConfig failed: %v", err)
	}
	if spec.BrainID != "trading-brain" {
		t.Errorf("Expected BrainID 'trading-brain' from standalone.yaml with zero env vars, got %q", spec.BrainID)
	}
}

// -----------------------------------------------------------------------------

func TestBuildSpecFromConfig_DockerMFEURLResolution(t *testing.T) {
	tmpDir := t.TempDir()
	yamlPath := filepath.Join(tmpDir, "docker.yaml")
	yamlContent := `common:
  name: watchdog_agent
  public_ip: 127.0.0.2
capabilities:
  config_server:
    ip: 0.0.0.0
    port: 3306
    rest_port: 3308
  watchdog_agent:
    ip: log-shipper
    port: 9090
    rest_port: 9095
  ipv6_svc:
    ip: "::"
    port: 7000
    rest_port: 7001
`
	if err := os.WriteFile(yamlPath, []byte(yamlContent), 0644); err != nil {
		t.Fatalf("Failed to write docker.yaml: %v", err)
	}

	t.Setenv("CONFIG_PATH", yamlPath)
	t.Setenv("SHARED_CONFIG_PATH", "")
	t.Setenv("HOST_IP", "")
	t.Setenv("DOCKER_ENV", "true")

	appConfig, err := toolbox_config.LoadConfig("standalone", nil)
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	// 1. Wildcard 0.0.0.0 explicit MFE URL resolves to common.public_ip (127.0.0.2)
	cfgSpec, err := BuildSpecFromConfig(appConfig, "config_server", ServiceSpec{
		Name:        "Config Server",
		Tag:         "config-server-mfe",
		URL:         "http://0.0.0.0:3308/static/js/mfe-loader.js",
		Layer:       "L1",
		Category:    "Base Fleet",
		Description: "Config service.",
		Protocol:    "TCP & REST",
		Framing:     "Port %s TCP / Port %s REST",
		DocLink:     "obsidian-brain/06-Microservices/Config-Server-Hub.md",
	})
	if err != nil {
		t.Fatalf("BuildSpecFromConfig(config_server) failed: %v", err)
	}
	if cfgSpec.URL != "http://127.0.0.2:3308/static/js/mfe-loader.js" {
		t.Errorf("Expected http://127.0.0.2:3308/static/js/mfe-loader.js, got %q", cfgSpec.URL)
	}

	// 2. Docker single-label DNS host (log-shipper) resolves to common.public_ip (127.0.0.2)
	wdSpec, err := BuildSpecFromConfig(appConfig, "watchdog_agent", ServiceSpec{
		Name:        "Watchdog Agent",
		Tag:         "watchdog-agent-mfe",
		URL:         "http://log-shipper:9095/static/mfe.js",
		Layer:       "L1",
		Category:    "Base Fleet",
		Description: "Watchdog agent.",
		Protocol:    "HTTP/1.1 REST",
		Framing:     "Port %s REST",
		DocLink:     "obsidian-brain/06-Microservices/Watchdog-Agent-Hub.md",
	})
	if err != nil {
		t.Fatalf("BuildSpecFromConfig(watchdog_agent) failed: %v", err)
	}
	if wdSpec.URL != "http://127.0.0.2:9095/static/mfe.js" {
		t.Errorf("Expected http://127.0.0.2:9095/static/mfe.js, got %q", wdSpec.URL)
	}

	// 3. Auto-resolved empty URL with :: wildcard also resolves to 127.0.0.2
	v6Spec, err := BuildSpecFromConfig(appConfig, "ipv6_svc", ServiceSpec{
		Name:        "IPv6 Service",
		Tag:         "ipv6-svc-mfe",
		Layer:       "L2",
		Category:    "Domain Services",
		Description: "IPv6 test service.",
		Protocol:    "REST",
		Framing:     "Port %s REST",
		DocLink:     "doc.md",
	})
	if err != nil {
		t.Fatalf("BuildSpecFromConfig(ipv6_svc) failed: %v", err)
	}
	if v6Spec.URL != "http://127.0.0.2:7001" {
		t.Errorf("Expected http://127.0.0.2:7001, got %q", v6Spec.URL)
	}

	// 4. HOST_IP overrides common.public_ip when set
	t.Setenv("HOST_IP", "203.0.113.10")
	if got := ResolveMFEURL(appConfig, "http://log-shipper:9095/static/mfe.js"); got != "http://203.0.113.10:9095/static/mfe.js" {
		t.Errorf("Expected HOST_IP override http://203.0.113.10:9095/static/mfe.js, got %q", got)
	}

	// 5. Relative path and non-Docker mode remain untouched
	if got := ResolveMFEURL(appConfig, "/static/mfe.js"); got != "/static/mfe.js" {
		t.Errorf("Expected relative URL untouched, got %q", got)
	}
	t.Setenv("DOCKER_ENV", "")
	if got := ResolveMFEURL(appConfig, "http://log-shipper:9095/static/mfe.js"); got != "http://log-shipper:9095/static/mfe.js" {
		t.Errorf("Expected URL untouched outside Docker, got %q", got)
	}

	// 6. Zero silent fallback when both HOST_IP and common.public_ip are empty
	t.Setenv("DOCKER_ENV", "true")
	t.Setenv("HOST_IP", "")
	appConfig.Config.Common.PublicIP = ""
	if got := ResolveMFEURL(appConfig, "http://0.0.0.0:3308/static/js/mfe-loader.js"); got != "http://0.0.0.0:3308/static/js/mfe-loader.js" {
		t.Errorf("Expected no silent 127.0.0.2 fallback when public_ip and HOST_IP are empty, got %q", got)
	}
}
