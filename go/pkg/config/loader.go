package config

import (
	"fmt"
	"os"

	distconf "github.com/Bastien-Antigravity/distributed-config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/connectivity"
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
	fmt.Printf("Toolbox: Initializing Config with Profile: %s\n", profile)

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
	// In Dev (Standalone/Test): File > Server
	// In Prod (Production/Preprod): Server > File
	isDev := (profile == "standalone" || profile == "test")

	if isDev {
		fmt.Println("Toolbox: Dev Mode detected. Re-applying Local File as Hard Override.")
		ac.applyFileOverride(profile + ".yaml")
	} else {
		fmt.Println("Toolbox: Production Mode detected. Config Server remains authoritative.")
	}

	// Phase 4: Apply CLI Overrides (Highest)
	ac.applyCLIOverrides(cliArgs)
	ac.applyCLIGRPCOverrides(cliArgs)

	return ac, nil
}

func (ac *AppConfig) applyFileOverride(filename string) {
	data, err := os.ReadFile(filename)
	if err != nil {
		return // Ignore if file missing, we already have dConf defaults
	}

	var raw map[string]interface{}
	if err := yaml.Unmarshal(data, &raw); err == nil {
		// Merge Capabilities
		if caps, ok := raw["capabilities"].(map[string]interface{}); ok {
			ac.Config.Capabilities = DeepMerge(ac.Config.Capabilities, caps)
		}
	}
}

func (ac *AppConfig) applyCLIOverrides(args *CLIArgs) {
	if args.Name != "" {
		ac.Config.Common.Name = args.Name
	}

	// Host and Port are usually inside the capability matching the service name or 'config_server'
	if args.Host != "" || args.Port != 0 {
		// Identify the target capability to override (defaults to current Name or config_server)
		target := args.Name
		if target == "" {
			target = "config_server" // fallback for many of your components
		}
		
		capMap, ok := ac.Config.Capabilities[target].(map[string]interface{})
		if !ok {
			capMap = make(map[string]interface{})
		}
		
		if args.Host != "" {
			capMap["ip"] = args.Host
		}
		if args.Port != 0 {
			capMap["port"] = fmt.Sprintf("%d", args.Port)
		}
		
		ac.Config.Capabilities[target] = capMap
	}
}

func (ac *AppConfig) applyCLIGRPCOverrides(args *CLIArgs) {
	target := args.Name
	if target == "" {
		target = "config_server" // default target for overrides if name not specified
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

// GetListenAddr extracts a capability and resolves its IP for binding.
func (ac *AppConfig) GetListenAddr(capability string) (string, error) {
	return ac.getAddr(capability, "ip", "port")
}

func (ac *AppConfig) GetGRPCListenAddr(capability string) (string, error) {
	return ac.getAddr(capability, "grpc_ip", "grpc_port")
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
	port := "8080"
	if p, ok := cap[portKey].(string); ok && p != "" {
		port = p
	}

	return fmt.Sprintf("%s:%s", host, port), nil
}

// GetDiscoveryAddr extracts a capability and resolves its address for clients.
// Note: In Docker, this can be overridden to return the service name if desired,
// but usually Docker DNS handles the mapping from name to IP automatically.
func (ac *AppConfig) GetDiscoveryAddr(capability string) (string, error) {
	var cap struct {
		IP   string `json:"ip"`
		Port string `json:"port"`
	}

	if err := ac.GetCapability(capability, &cap); err != nil {
		return "", err
	}

	return fmt.Sprintf("%s:%s", cap.IP, cap.Port), nil
}
