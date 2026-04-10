package config

import (
	"fmt"

	distconf "github.com/Bastien-Antigravity/distributed-config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/connectivity"
)

// AppConfig wraps the distributed-config and provides toolbox enhancements.
type AppConfig struct {
	*distconf.Config
	Resolver *connectivity.Resolver
}

// LoadConfig loads the distributed configuration and initializes the toolbox helper.
func LoadConfig(profile string) (*AppConfig, error) {
	dConf := distconf.New(profile)
	if dConf == nil {
		return nil, fmt.Errorf("failed to load distributed config for profile: %s", profile)
	}

	return &AppConfig{
		Config:   dConf,
		Resolver: connectivity.NewResolver(),
	}, nil
}

// GetListenAddr extracts a capability and resolves its IP for binding.
func (ac *AppConfig) GetListenAddr(capability string) (string, error) {
	var cap struct {
		IP   string `json:"ip"`
		Port string `json:"port"`
	}

	if err := ac.GetCapability(capability, &cap); err != nil {
		return "", err
	}

	bindIP, err := ac.Resolver.ResolveBindAddr(cap.IP)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf("%s:%s", bindIP, cap.Port), nil
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
