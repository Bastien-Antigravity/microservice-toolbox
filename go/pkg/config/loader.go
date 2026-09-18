// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Loads layered configuration from local YAML, environment variables, and distributed config server.
//
// DATA FLOW:
// YAML File / Env Vars / Remote Server -> Config Parsing -> AppConfig Instance
//
// KEY PARAMETERS:
// - profile: Configuration profile (standalone, test, staging, production).
// - data: In-memory configuration key-value tree.
// -----------------------------------------------------------------------------

package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/connectivity"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"

	distributed_config "github.com/Bastien-Antigravity/distributed-config"

	"gopkg.in/yaml.v3"
)

// AppConfig wraps the distributed-config and provides toolbox enhancements.
type AppConfig struct {
	*distributed_config.Config
	Local    map[string]interface{}
	Resolver *connectivity.Resolver
	Profile  string
	Logger   logger.Logger
	Args     *CLIArgs
}

// GetServiceName returns the standardized program name.
func (ac *AppConfig) GetServiceName() string {
	if ac.Common.Name != "" {
		return ac.Common.Name
	}
	return "unknown-service"
}

// SetLogger updates the logger after instantiation.
func (ac *AppConfig) SetLogger(l logger.Logger) {
	ac.Logger = logger.EnsureSafeLogger(l)
	ac.Logger.Info("Logger updated successfully")
}

// LoadConfig loads the configuration with layered priority:
// 1. CLI Flags (Highest)
// 2. Layered Merge (File/Server based on Profile)
// 3. Env Vars (Lowest)
// LoadConfig loads the configuration with layered priority.
func LoadConfig(profile string, specificFlags []string) (*AppConfig, error) {
	return LoadConfigWithLogger(profile, nil, specificFlags)
}

// LoadConfigWithLogger loads the configuration with an explicit logger and layered priority.
func LoadConfigWithLogger(profile string, l logger.Logger, specificFlags []string) (*AppConfig, error) {
	safeLogger := logger.EnsureSafeLogger(l)

	// Step 0: Preliminary CLI Parse to handle --profile override
	tempAC := &AppConfig{
		Logger:   safeLogger,
		Resolver: connectivity.NewResolver(),
	}
	cliArgs := tempAC.ParseCLIArgs(specificFlags)

	actualProfile := profile
	if cliArgs.Profile != "" {
		actualProfile = cliArgs.Profile
	}

	safeLogger.Info("Initializing Config with Profile: %s", actualProfile)

	// Phase 1: Base Configuration (Initialize Distributed Config)
	// This loads the base YAML and performs initial Remote Sync if necessary.
	dConf := distributed_config.New(actualProfile)
	if dConf == nil {
		return nil, fmt.Errorf("failed to load distributed config for profile: %s", actualProfile)
	}

	ac := &AppConfig{
		Config:   dConf,
		Resolver: connectivity.NewResolver(),
		Profile:  actualProfile,
		Logger:   safeLogger,
		Args:     cliArgs,
	}

	// Phase 2: Local Overrides (Developer-Intent Parity)
	// We re-apply the local file as a hard override to ensure the 'local' section
	// and any local overrides are loaded across all profiles.
	ac.Logger.Info("Applying Local File as Hard Override (Ecosystem Parity).")
	ac.applyFileOverride(actualProfile + ".yaml")

	// Phase 3: CLI Arguments (Highest Priority)
	ac.applyCLIOverrides(cliArgs)
	ac.applyCLIGRPCOverrides(cliArgs)

	// Inject the manually defined local config from the test if it was set before LoadConfig (though unlikely in prod)
	// but mostly to ensure we don't wipe it out if it was already there.
	if tempAC.Local != nil {
		ac.Local = DeepMerge(ac.Local, tempAC.Local)
	}

	// Ensure the service name is synchronized to the base common config
	if cliArgs.Name != "" {
		ac.Common.Name = cliArgs.Name
	}

	// Phase 4: Remote Sync (Managed by the base Distributed Config)
	// The sync happened in Phase 1, but we ensure consistency here.

	// Phase 5: Security & Keys
	ac.loadPublicKey()

	// If --key flag provided, set it as ENV override for the Private Key (decryption engine)
	if cliArgs.Key != "" {
		_ = os.Setenv("BASTIEN_PRIVATE_KEY_PATH", cliArgs.Key)
	}

	if err := ac.ValidateUniquePorts(); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %w", err)
	}

	return ac, nil
}

func (ac *AppConfig) loadPublicKey() {
	path := os.Getenv("BASTIEN_PUBLIC_KEY_PATH")
	if path == "" {
		candidates := []string{"/etc/bastien/public.pem", "./public.pem"}
		for _, c := range candidates {
			if _, err := os.Stat(c); err == nil {
				path = c
				break
			}
		}
	}

	if path != "" {
		if content, err := os.ReadFile(path); err == nil {
			ac.Config.Common.PublicKey = string(content)
		}
	}
}

func (ac *AppConfig) applyFileOverride(filename string) {
	// Build search candidates (matches distributed-config logic)
	targetName := strings.TrimSuffix(filename, filepath.Ext(filename))
	path := distributed_config.ResolveConfigPath(targetName)

	data, err := os.ReadFile(path)
	if err != nil {
		return
	}

	var root yaml.Node
	if err := yaml.Unmarshal(data, &root); err != nil {
		return
	}

	// Expand Environment Variables and force types using Distributed Config's logic
	distributed_config.ProcessNode(&root)

	// Decode into a generic map to extract sections
	var raw map[string]interface{}
	if err := root.Decode(&raw); err != nil {
		return
	}

	// Extract sections
	if caps, ok := raw["capabilities"].(map[string]interface{}); ok {
		ac.Config.Capabilities = DeepMerge(ac.Config.Capabilities, caps)
	}
	if comm, ok := raw["common"].(map[string]interface{}); ok {
		if name, ok := comm["name"].(string); ok {
			ac.Config.Common.Name = name
		}
	}
	if priv, ok := raw["local"].(map[string]interface{}); ok {
		if ac.Local == nil {
			ac.Local = make(map[string]interface{})
		}
		ac.Local = DeepMerge(ac.Local, priv)
	}
}

// GetLocal returns a value from the 'local' configuration section.
// Supports nested lookups using dot notation (e.g., "database.host").
func (ac *AppConfig) GetLocal(key string) interface{} {
	if ac == nil || ac.Local == nil {
		return nil
	}

	parts := strings.Split(key, ".")
	var current interface{} = ac.Local

	for _, part := range parts {
		if m, ok := current.(map[string]interface{}); ok {
			if val, exists := m[part]; exists {
				current = val
			} else {
				return nil
			}
		} else {
			return nil
		}
	}

	return current
}

// UnmarshalLocal maps the 'local' configuration section into a target struct.
func (ac *AppConfig) UnmarshalLocal(target interface{}) error {
	if ac.Local == nil {
		return fmt.Errorf("no local configuration found")
	}
	data, err := yaml.Marshal(ac.Local)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(data, target)
}

// DecryptSecret decrypts a single ENC(...) ciphertext string.
// If the string does not start with ENC(...), it is returned as-is (plaintext fallback).
// If it is an ENC(...) block but decryption fails, an error is returned.
func (ac *AppConfig) DecryptSecret(ciphertext string) (string, error) {
	if !strings.HasPrefix(ciphertext, "ENC(") || !strings.HasSuffix(ciphertext, ")") {
		return ciphertext, nil
	}
	return distributed_config.Decrypt(ciphertext)
}

// OnLiveConfUpdate registers a callback for live configuration updates.
func (ac *AppConfig) OnLiveConfUpdate(cb func(map[string]interface{})) {
	ac.Config.OnLiveConfUpdate(func(data map[string]map[string]string) {
		// Convert to generic map for the toolbox's uniform API
		generic := make(map[string]interface{})
		for k, v := range data {
			inner := make(map[string]interface{})
			for ik, iv := range v {
				inner[ik] = iv
			}
			generic[k] = inner
		}
		cb(generic)
	})
}

// OnRegistryUpdate registers a callback for service registry changes.
func (ac *AppConfig) OnRegistryUpdate(cb func(map[string]interface{})) {
	ac.Config.OnRegistryUpdate(func(data map[string][]string) {
		generic := make(map[string]interface{})
		for k, v := range data {
			generic[k] = v
		}
		cb(generic)
	})
}

// ShareConfig shares service configuration with the ecosystem.
func (ac *AppConfig) ShareConfig(payload map[string]interface{}) error {
	return ac.Config.ShareConfig(payload)
}

func (ac *AppConfig) applyCLIOverrides(args *CLIArgs) {
	if args.Name != "" {
		ac.Config.Common.Name = args.Name
	}

	target := args.Name
	if target == "" {
		target = ac.Config.Common.Name
	}
	if target == "" {
		target = "config_server"
	}

	if args.Host != "" || args.Port != 0 {
		ac.ensurePath("capabilities." + target)
		cap := ac.Config.Capabilities[target].(map[string]interface{})
		if args.Host != "" {
			cap["ip"] = args.Host
		}
		if args.Port != 0 {
			cap["port"] = fmt.Sprintf("%d", args.Port)
		}
	}
}

func (ac *AppConfig) applyCLIGRPCOverrides(args *CLIArgs) {
	target := args.Name
	if target == "" {
		target = ac.Config.Common.Name
	}
	if target == "" {
		target = "config_server"
	}

	if args.GRPCHost != "" || args.GRPCPort != 0 {
		ac.ensurePath("capabilities." + target)
		cap := ac.Config.Capabilities[target].(map[string]interface{})
		if args.GRPCHost != "" {
			cap["grpc_ip"] = args.GRPCHost
		}
		if args.GRPCPort != 0 {
			cap["grpc_port"] = fmt.Sprintf("%d", args.GRPCPort)
		}
	}
}

func (ac *AppConfig) ensurePath(path string) {
	if ac.Config.Capabilities == nil {
		ac.Config.Capabilities = make(map[string]interface{})
	}
	parts := strings.Split(path, ".")
	if len(parts) < 2 {
		return
	}
	// Currently we only support capabilities.NAME
	if parts[0] == "capabilities" {
		target := parts[1]
		if _, ok := ac.Config.Capabilities[target].(map[string]interface{}); !ok {
			ac.Config.Capabilities[target] = make(map[string]interface{})
		}
	}
}

func (ac *AppConfig) GetListenAddr(capability string) (string, error) {
	return ac.Config.GetAddress(capability)
}

func (ac *AppConfig) GetGRPCListenAddr(capability string) (string, error) {
	return ac.Config.GetGRPCAddress(capability)
}

// GetRESTAddr returns the address for the REST management interface.
func (ac *AppConfig) GetRESTAddr(capability string) (string, error) {
	return ac.Config.GetRESTAddress(capability)
}


type endpointKey struct {
	IP   string
	Port int
}

func normalizeIP(ip string) string {
	ip = strings.TrimSpace(strings.ToLower(ip))
	if ip == "localhost" {
		return "127.0.0.1"
	}
	return ip
}

func getPort(val interface{}) (int, bool) {
	if val == nil {
		return 0, false
	}
	switch v := val.(type) {
	case int:
		return v, true
	case int64:
		return int(v), true
	case float64:
		return int(v), true
	case string:
		p, err := strconv.Atoi(v)
		if err == nil {
			return p, true
		}
	}
	return 0, false
}

func getIP(val interface{}) string {
	if val == nil {
		return ""
	}
	return fmt.Sprintf("%v", val)
}

func (ac *AppConfig) ValidateUniquePorts() error {
	if ac.Config == nil || ac.Config.Capabilities == nil {
		return nil
	}

	seen := make(map[endpointKey]string)

	checkAndAdd := func(ip string, port int, desc string) error {
		nip := normalizeIP(ip)
		for seenKey, seenDesc := range seen {
			if seenKey.Port == port {
				if nip == seenKey.IP || nip == "0.0.0.0" || seenKey.IP == "0.0.0.0" {
					return fmt.Errorf("duplicate endpoint detected: %s:%d for %s conflicts with %s:%d for %s", ip, port, desc, seenKey.IP, seenKey.Port, seenDesc)
				}
			}
		}
		seen[endpointKey{IP: nip, Port: port}] = desc
		return nil
	}

	for capName, capVal := range ac.Config.Capabilities {
		capMap, ok := capVal.(map[string]interface{})
		if !ok {
			continue
		}

		ip := getIP(capMap["ip"])
		gIP := getIP(capMap["grpc_ip"])
		if gIP == "" {
			gIP = ip
		}

		// Explicit TCP port
		if port, ok := getPort(capMap["port"]); ok && ip != "" {
			if err := checkAndAdd(ip, port, fmt.Sprintf("%s (TCP)", capName)); err != nil {
				return err
			}
		}

		// Explicit gRPC port
		if gp, ok := getPort(capMap["grpc_port"]); ok && gIP != "" {
			if err := checkAndAdd(gIP, gp, fmt.Sprintf("%s (gRPC)", capName)); err != nil {
				return err
			}
		}

		// Explicit REST port
		if rp, ok := getPort(capMap["rest_port"]); ok && ip != "" {
			if err := checkAndAdd(ip, rp, fmt.Sprintf("%s (REST)", capName)); err != nil {
				return err
			}
		}
	}
	return nil
}
