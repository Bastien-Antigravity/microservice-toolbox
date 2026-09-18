package bootstrap

// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized entrypoint and bootstrap ritual for Go microservices in the
// Bastien-Antigravity fleet. Auto-detects runtime environment (Local vs Docker),
// loads layered distributed configuration, and binds Universal Logger.
//
// DATA FLOW:
// CLI / OS Environment -> LoadConfig() -> unilog.InitWithOptions() -> (AppConfig, Logger)
//
// KEY PARAMETERS:
// - serviceName: Unique identifier for the microservice.
// - specificFlags: Optional CLI arguments passed to configuration loader.
// -----------------------------------------------------------------------------

import (
	"fmt"
	"os"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	unilog "github.com/Bastien-Antigravity/universal-logger/src/bootstrap"
	unilog_config "github.com/Bastien-Antigravity/universal-logger/src/config"
	unilog_interfaces "github.com/Bastien-Antigravity/universal-logger/src/interfaces"
	unilog_utils "github.com/Bastien-Antigravity/universal-logger/src/utils"
)

// BootstrapServiceSafe initializes AppConfig and Universal Logger without calling os.Exit.
// Returns an error if configuration loading fails.
func BootstrapServiceSafe(serviceName string, specificFlags ...string) (*toolbox_config.AppConfig, unilog_interfaces.Logger, error) {
	profile := "standalone"
	loggerProfile := "standard"

	if os.Getenv("DOCKER_ENV") == "true" || os.Getenv("CONTAINER") == "true" {
		profile = "production"
		loggerProfile = "cloud"
	}
	if lp := os.Getenv("LOGGER_PROFILE"); lp != "" {
		loggerProfile = lp
	}

	appConfig, err := toolbox_config.LoadConfig(profile, specificFlags)
	if err != nil {
		return nil, nil, fmt.Errorf("loading config for service %s: %w", serviceName, err)
	}

	logLevel := os.Getenv("LOG_LEVEL")
	if logLevel == "" {
		logLevel = "INFO"
	}

	_, appLogger := unilog.InitWithOptions(unilog.BootstrapOptions{
		Name:             serviceName,
		ConfigProfile:    appConfig.Profile,
		LoggerProfile:    loggerProfile,
		InitialLogLevel:  unilog_utils.GetLogLevel(logLevel),
		UseLocalNotifier: true,
		ExistingConfig:   &unilog_config.DistConfig{Config: appConfig.Config},
	})

	appConfig.Logger = appLogger
	return appConfig, appLogger, nil
}

// -----------------------------------------------------------------------------

// BootstrapService provides a standardized 1-line entrypoint for Go microservices.
// It auto-detects environment (DEV vs PROD/Docker), loads AppConfig, and binds Universal Logger.
// For graceful error returns without process exit, use BootstrapServiceSafe.
func BootstrapService(serviceName string, specificFlags ...string) (*toolbox_config.AppConfig, unilog_interfaces.Logger) {
	appConfig, appLogger, err := BootstrapServiceSafe(serviceName, specificFlags...)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Critical Error: %v\n", err)
		os.Exit(1)
	}
	return appConfig, appLogger
}
