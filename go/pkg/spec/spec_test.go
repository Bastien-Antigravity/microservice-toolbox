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
	if err != nil {
		t.Fatalf("Failed to load standalone config: %v", err)
	}
	delete(appConfig.Capabilities, "web_interface")

	err = PublishSync(context.Background(), appConfig, nil, "config_server", validBase)
	if err == nil {
		t.Errorf("PublishSync must FAIL FAST when web_interface is missing from configuration")
	}
	if !strings.Contains(err.Error(), "web_interface") {
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
	if err != nil {
		t.Fatalf("Failed to load standalone config: %v", err)
	}
	if appConfig.Capabilities == nil {
		appConfig.Capabilities = make(map[string]interface{})
	}
	parts := strings.Split(serverAddr, ":")
	portNum := 0
	if len(parts) == 2 {
		var p int
		json.Unmarshal([]byte(parts[1]), &p)
		portNum = p
	}
	appConfig.Capabilities["web_interface"] = map[string]interface{}{
		"ip":   parts[0],
		"port": portNum,
	}

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
