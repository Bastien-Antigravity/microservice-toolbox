package config

import (
	"fmt"
	"os"

	"github.com/spf13/pflag"
)

// CLIArgs holds the standard microservice arguments.
type CLIArgs struct {
	Name     string
	Host     string
	Port     int
	GRPCHost string
	GRPCPort int
	Conf     string
	LogLevel string
	Key      string
	Extra    map[string]string
}

// ParseCLIArgs parses standard and specific command line arguments.
// It implements a "Docker Guard": if DOCKER_ENV=true, --host and --port are ignored.
func (ac *AppConfig) ParseCLIArgs(specificFlags []string) *CLIArgs {
	fs := pflag.NewFlagSet(os.Args[0], pflag.ContinueOnError)

	// Standard flags
	name := fs.String("name", "", "Service name")
	host := fs.String("host", "", "Binding host IP")
	port := fs.Int("port", 0, "Binding port")
	grpcHost := fs.String("grpc_host", "", "GRPC Binding host IP")
	grpcPort := fs.Int("grpc_port", 0, "GRPC Binding port")
	conf := fs.String("conf", "", "Path to configuration file")
	logLevel := fs.String("log_level", "", "Logging level (DEBUG, INFO, etc.)")
	key := fs.String("key", "", "Path to RSA Public/Private key")

	// Dynamic flags for extra arguments
	extras := make(map[string]*string)
	for _, f := range specificFlags {
		extras[f] = fs.String(f, "", fmt.Sprintf("Specific flag: %s", f))
	}

	// Parse
	if err := fs.Parse(os.Args[1:]); err != nil {
		if err == pflag.ErrHelp {
			os.Exit(0)
		}
		ac.Logger.Error("Error parsing flags: %v", err)
	}

	result := &CLIArgs{
		Name:     *name,
		Conf:     *conf,
		LogLevel: *logLevel,
		Key:      *key,
		Extra:    make(map[string]string),
	}

	// If key provided, set it as ENV override for the decryption engine (Private Key)
	if *key != "" {
		os.Setenv("BASTIEN_PRIVATE_KEY_PATH", *key)
	}

	// Apply Docker Guard
	if ac.Resolver.IsDocker {
		if *host != "" || *port != 0 || *grpcHost != "" || *grpcPort != 0 {
			ac.Logger.Info("Toolbox: Running in Docker. Ignoring CLI overrides for network flags to preserve network-aware resolution.")
		}
		result.Host = ""
		result.Port = 0
		result.GRPCHost = ""
		result.GRPCPort = 0
	} else {
		result.Host = *host
		result.Port = *port
		result.GRPCHost = *grpcHost
		result.GRPCPort = *grpcPort
	}

	result.Conf = *conf
	for k, v := range extras {
		result.Extra[k] = *v
	}

	return result
}
