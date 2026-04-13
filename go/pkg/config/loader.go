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
	Logger   utils.Logger
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
	dConf := distconf.New(profile)
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
	return ac.Config.GetAddress(capability)
}

func (ac *AppConfig) GetGRPCListenAddr(capability string) (string, error) {
	return ac.Config.GetGRPCAddress(capability)
}
