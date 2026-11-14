// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Resolves configured capability network addresses strictly from AppConfig inputs.
//
// DATA FLOW:
// Config Address Input -> Validation + Host/Port Split -> Final Bind Address
//
// KEY PARAMETERS:
// - requestedIP: Configured IP/host from AppConfig (zero hardcoded defaults).
// -----------------------------------------------------------------------------

package connectivity

import (
	"fmt"
	"net"
	"os"
	"strings"
)

// Resolver handles network address resolution strictly from configuration.
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

// IsDockerEnv returns whether the resolver detected or was configured for a Docker environment.
func (r *Resolver) IsDockerEnv() bool {
	return r.IsDocker
}

// ResolveBindAddr validates and returns the configured IP without substituting any hardcoded default.
func (r *Resolver) ResolveBindAddr(requestedIP string) (string, error) {
	if strings.TrimSpace(requestedIP) == "" {
		return "", fmt.Errorf("connectivity.ResolveBindAddr: configured bind IP must not be empty (FAIL-FAST)")
	}
	return requestedIP, nil
}

// ResolveFullBindAddr validates and returns a configured "host:port", "[ipv6]:port", or bare host string.
func (r *Resolver) ResolveFullBindAddr(addr string) (string, error) {
	if strings.TrimSpace(addr) == "" {
		return "", fmt.Errorf("connectivity.ResolveFullBindAddr: configured bind address must not be empty (FAIL-FAST)")
	}

	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		// If no port specified, treat the whole string as host
		return r.ResolveBindAddr(addr)
	}
	if strings.TrimSpace(port) == "" {
		return "", fmt.Errorf("connectivity.ResolveFullBindAddr: configured bind port must not be empty in %q (FAIL-FAST)", addr)
	}

	resolvedHost, err := r.ResolveBindAddr(host)
	if err != nil {
		return "", err
	}

	return net.JoinHostPort(resolvedHost, port), nil
}

// IsLoopback checks if the IP or hostname refers to a loopback address.
func (r *Resolver) IsLoopback(ip string) bool {
	return strings.HasPrefix(ip, "127.") || ip == "::1" || strings.EqualFold(ip, "localhost")
}

// isLoopback delegates to IsLoopback for package-internal compatibility.
func (r *Resolver) isLoopback(ip string) bool {
	return r.IsLoopback(ip)
}

// GetPrimaryInterfaceIP finds the first non-loopback IPv4 interface address.
func (r *Resolver) GetPrimaryInterfaceIP() (string, error) {
	ifaces, err := net.Interfaces()
	if err != nil {
		return "", err
	}

	for _, i := range ifaces {
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

			ip = ip.To4()
			if ip != nil {
				return ip.String(), nil
			}
		}
	}

	return "", fmt.Errorf("no primary network interface found")
}

// getPrimaryInterfaceIP delegates to GetPrimaryInterfaceIP for internal compatibility.
func (r *Resolver) getPrimaryInterfaceIP() (string, error) {
	return r.GetPrimaryInterfaceIP()
}
