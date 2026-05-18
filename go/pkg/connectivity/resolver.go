package connectivity

import (
	"fmt"
	"net"
	"os"
	"strings"
)

// Resolver handles environment-aware network address translation.
type Resolver struct {
	// IsDocker indicates if the current environment is a Docker container.
	IsDocker bool
}

// NewResolver creates a new network resolver.
func NewResolver() *Resolver {
	// Detect Docker environment
	_, err := os.Stat("/.dockerenv")
	return &Resolver{
		IsDocker: err == nil || os.Getenv("DOCKER_ENV") == "true",
	}
}

// ResolveBindAddr resolves the requested IP into an actual address to bind to.
//
// Docker Guard Logic:
// If running in a Docker container, this method suppresses the requested IP
// and forces a bind to 0.0.0.0. This ensures that the container port mapping
// (Docker/K8s) works regardless of what was specified in the configuration.
func (r *Resolver) ResolveBindAddr(requestedIP string) (string, error) {
	requestedIP = strings.Trim(requestedIP, "\"")

	// If not in Docker, use the requested IP directly.
	if !r.IsDocker {
		return requestedIP, nil
	}

	// In Docker, we force 0.0.0.0 to ensure orchestrated networking works.
	// This "suppresses" any manual IP overrides.
	return "0.0.0.0", nil
}

// ResolveFullBindAddr takes a "host:port" string and returns a resolved "host:port"
// using the Docker Guard logic.
func (r *Resolver) ResolveFullBindAddr(addr string) (string, error) {
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		// If no port specified, treat the whole string as host
		resolvedHost, err := r.ResolveBindAddr(addr)
		return resolvedHost, err
	}

	resolvedHost, err := r.ResolveBindAddr(host)
	if err != nil {
		return "", err
	}

	return net.JoinHostPort(resolvedHost, port), nil
}

// isLoopback checks if the IP is in the 127.0.0.0/8 range.
func (r *Resolver) isLoopback(ip string) bool {
	return strings.HasPrefix(ip, "127.") || ip == "::1" || ip == "localhost"
}

// getPrimaryInterfaceIP finds the first non-loopback IP address.
// Keep as utility for potential client-side discovery.
func (r *Resolver) getPrimaryInterfaceIP() (string, error) {
	ifaces, err := net.Interfaces()
	if err != nil {
		return "", err
	}

	for _, i := range ifaces {
		// Skip loopback and down interfaces
		if i.Flags&net.FlagLoopback != 0 || i.Flags&net.FlagUp == 0 {
			continue
		}

		addrs, err := i.Addrs()
		if err != nil {
			continue
		}

		for _, addr := range addrs {
			var ip net.IP
			switch v := addr.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}

			if ip == nil || ip.IsLoopback() {
				continue
			}

			// Return the first internal IPv4 address found (standard Docker behavior)
			ip = ip.To4()
			if ip != nil {
				return ip.String(), nil
			}
		}
	}

	return "", fmt.Errorf("no primary network interface found")
}
