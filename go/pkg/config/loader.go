package config

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/connectivity"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/utils"

	distributed_config "github.com/Bastien-Antigravity/distributed-config"

	"gopkg.in/yaml.v3"
)

// AppConfig wraps the distributed-config and provides toolbox enhancements.
type AppConfig struct {
	*distributed_config.Config
	Local    map[string]interface{}
	Resolver *connectivity.Resolver
	Profile  string
	Logger   utils.Logger
}

// SetLogger updates the logger after instantiation.
func (ac *AppConfig) SetLogger(logger utils.Logger) {
	ac.Logger = utils.EnsureSafeLogger(logger)
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
func LoadConfigWithLogger(profile string, logger utils.Logger, specificFlags []string) (*AppConfig, error) {
	safeLogger := utils.EnsureSafeLogger(logger)
	safeLogger.Info("Initializing Config with Profile: %s", profile)

	// Phase 1: Initialize Distributed Config (Base + Env Templates + Server Sync)
	dConf := distributed_config.New(profile)
	if dConf == nil {
		return nil, fmt.Errorf("failed to load distributed config for profile: %s", profile)
	}

	ac := &AppConfig{
		Config:   dConf,
		Resolver: connectivity.NewResolver(),
		Profile:  profile,
		Logger:   safeLogger,
	}

	// Phase 2: Handle CLI Flags
	cliArgs := ac.ParseCLIArgs(specificFlags)

	// Phase 3: Layered Merging Logic
	isDev := (profile == "standalone" || profile == "test")

	if isDev {
		ac.Logger.Info("Dev Mode detected. Re-applying Local File as Hard Override.")
		ac.applyFileOverride(profile + ".yaml")
	} else {
		ac.Logger.Info("Production Mode detected. Config Server remains authoritative.")
	}

	// Phase 4: Apply CLI Overrides (Highest)
	ac.applyCLIOverrides(cliArgs)
	ac.applyCLIGRPCOverrides(cliArgs)

	// Phase 5: Public Key Auto-Discovery
	ac.loadPublicKey()

	// If --key flag provided, set it as ENV override for the Private Key (decryption engine)
	if cliArgs.Key != "" {
		os.Setenv("BASTIEN_PRIVATE_KEY_PATH", cliArgs.Key)
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
	data, err := os.ReadFile(filename)
	if err != nil {
		return
	}

	var root yaml.Node
	if err := yaml.Unmarshal(data, &root); err != nil {
		return
	}

	// Expand Environment Variables and force types using Distributed Config's logic
	distributed_config.ProcessNode(&root)

	var raw map[string]interface{}
	if err := root.Decode(&raw); err == nil {
		if caps, ok := raw["capabilities"].(map[string]interface{}); ok {
			ac.Config.Capabilities = DeepMerge(ac.Config.Capabilities, caps)
		}
		if priv, ok := raw["local"].(map[string]interface{}); ok {
			if ac.Local == nil {
				ac.Local = make(map[string]interface{})
			}
			ac.Local = DeepMerge(ac.Local, priv)
		}
	}
}

// GetLocal returns a value from the 'local' configuration section.
// Supports nested lookups using dot notation (e.g., "database.host").
func (ac *AppConfig) GetLocal(key string) interface{} {
	if ac.Local == nil {
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
	data, err := json.Marshal(ac.Local)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, target)
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
