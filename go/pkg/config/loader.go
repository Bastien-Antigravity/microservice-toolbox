package config

import (
	"fmt"
	"os"
	"strings"

	distconf "github.com/Bastien-Antigravity/distributed-config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/connectivity"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/utils"
	"gopkg.in/yaml.v3"
)

// AppConfig wraps the distributed-config and provides toolbox enhancements.
type AppConfig struct {
	*distconf.Config
	Resolver *connectivity.Resolver
	Profile  string
}

// LoadConfig loads the configuration with layered priority:
// 1. CLI Flags (Highest)
// 2. Layered Merge (File/Server based on Profile)
// 3. Env Vars (Lowest)
func LoadConfig(profile string, specificFlags []string) (*AppConfig, error) {
	utils.PrintInternalLog("INFO", "loader.go", "loader.go", "25", fmt.Sprintf("Initializing Config with Profile: %s", profile))

	// Phase 1: Initialize Distributed Config (Base + Env Templates + Server Sync)
	dConf := distconf.New(profile)
	if dConf == nil {
		return nil, fmt.Errorf("failed to load distributed config for profile: %s", profile)
	}

	ac := &AppConfig{
		Config:   dConf,
		Resolver: connectivity.NewResolver(),
		Profile:  profile,
	}

	// Phase 2: Handle CLI Flags
	cliArgs := ac.ParseCLIArgs(specificFlags)

	// Phase 3: Layered Merging Logic
	isDev := (profile == "standalone" || profile == "test")

	if isDev {
		utils.PrintInternalLog("INFO", "loader.go", "loader.go", "46", "Dev Mode detected. Re-applying Local File as Hard Override.")
		ac.applyFileOverride(profile + ".yaml")
	} else {
		utils.PrintInternalLog("INFO", "loader.go", "loader.go", "49", "Production Mode detected. Config Server remains authoritative.")
	}

	// Phase 4: Apply CLI Overrides (Highest)
	ac.applyCLIOverrides(cliArgs)
	ac.applyCLIGRPCOverrides(cliArgs)

	return ac, nil
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
	distconf.ProcessNode(&root)

	var raw map[string]interface{}
	if err := root.Decode(&raw); err == nil {
		if caps, ok := raw["capabilities"].(map[string]interface{}); ok {
			ac.Config.Capabilities = DeepMerge(ac.Config.Capabilities, caps)
		}
	}
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
	return ac.getAddr(capability, "ip", "port")
}

func (ac *AppConfig) GetGRPCListenAddr(capability string) (string, error) {
	addr, err := ac.getAddr(capability, "grpc_ip", "grpc_port")
	if err == nil {
		return addr, nil
	}

	// Fallback to convention: ip:port+1
	capRaw, ok := ac.Config.Capabilities[capability]
	if !ok {
		return "", fmt.Errorf("capability %s not found for gRPC fallback", capability)
	}
	cap := capRaw.(map[string]interface{})

	host := "0.0.0.0"
	if h, ok := cap["ip"].(string); ok && h != "" {
		host = h
	}

	port := 8080
	if p, ok := cap["port"].(string); ok && p != "" {
		fmt.Sscanf(p, "%d", &port)
	}

	return fmt.Sprintf("%s:%d", host, port+1), nil
}

func (ac *AppConfig) getAddr(capability, hostKey, portKey string) (string, error) {
	if ac.Config.Capabilities == nil {
		return "", fmt.Errorf("no capabilities found")
	}
	capRaw, ok := ac.Config.Capabilities[capability]
	if !ok {
		return "", fmt.Errorf("capability %s not found", capability)
	}

	cap, ok := capRaw.(map[string]interface{})
	if !ok {
		return "", fmt.Errorf("invalid capability format for %s", capability)
	}

	host := "0.0.0.0"
	if h, ok := cap[hostKey].(string); ok && h != "" {
		host = h
	}

	p, ok := cap[portKey].(string)
	if !ok || p == "" {
		return "", fmt.Errorf("port key %s missing or empty in capability %s", portKey, capability)
	}

	return fmt.Sprintf("%s:%s", host, p), nil
}
