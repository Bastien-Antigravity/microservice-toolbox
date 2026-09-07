package bootstrap

import (
	"fmt"
	"os"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	unilog "github.com/Bastien-Antigravity/universal-logger/src/bootstrap"
	unilog_config "github.com/Bastien-Antigravity/universal-logger/src/config"
	unilog_interfaces "github.com/Bastien-Antigravity/universal-logger/src/interfaces"
	unilog_utils "github.com/Bastien-Antigravity/universal-logger/src/utils"
)

// BootstrapService provides a standardized 1-line entrypoint for Go microservices.
// It auto-detects environment (DEV vs PROD/Docker), loads AppConfig, and binds Universal Logger.
func BootstrapService(serviceName string, specificFlags ...string) (*toolbox_config.AppConfig, unilog_interfaces.Logger) {
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
		fmt.Printf("Critical Error loading config for service %s: %v\n", serviceName, err)
		os.Exit(1)
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
	return appConfig, appLogger
}
