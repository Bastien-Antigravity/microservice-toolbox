package connectivity

import (
	"fmt"
	"net"
	"os"
	"strings"
)

// Resolver handles environment-aware network address translation.
type Resolver struct {
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
// If in Docker, it ignores loopback requests and finds the container's primary IP.
func (r *Resolver) ResolveBindAddr(requestedIP string) (string, error) {
	requestedIP = strings.Trim(requestedIP, "\"")

	// If not in Docker, or if the IP isn't a loopback placeholder, use it directly.
	if !r.IsDocker || !r.isLoopback(requestedIP) {
		return requestedIP, nil
	}

	// In Docker, we need the internal container IP (e.g., eth0) for other containers to reach us.
	// We specifically avoid 0.0.0.0 per user requirement.
	ip, err := r.getPrimaryInterfaceIP()
	if err != nil {
		return "", fmt.Errorf("failed to resolve container IP for bind: %w", err)
	}

	return ip, nil
}

// isLoopback checks if the IP is in the 127.0.0.0/8 range.
func (r *Resolver) isLoopback(ip string) bool {
	return strings.HasPrefix(ip, "127.") || ip == "::1" || ip == "localhost"
}

// getPrimaryInterfaceIP finds the first non-loopback IP address.
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
