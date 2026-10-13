// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Establishes and manages resilient connections to NATS message brokers.
//
// DATA FLOW:
// NatsConfig -> Connection Pool -> NATS Client Instance
//
// KEY PARAMETERS:
// - servers: Connection addresses for broker failover.
// -----------------------------------------------------------------------------

package messaging

import (
	"crypto/tls"
	"fmt"
	"strings"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
	"github.com/nats-io/nats.go"
)

// Connect establishes a connection to the NATS server using unified configuration options
// and routes NATS lifecycle events to the shared logger.
func Connect(cfg *NatsConfig, l logger.Logger) (*nats.Conn, error) {
	log := logger.EnsureSafeLogger(l)

	if len(cfg.Servers) == 0 {
		return nil, fmt.Errorf("no nats servers configured")
	}

	opts := []nats.Option{
		nats.Name(cfg.ClientID),
		nats.Timeout(cfg.ConnectTimeout),
		nats.ReconnectWait(cfg.ReconnectWait),
		nats.MaxReconnects(cfg.MaxReconnects),
		nats.FlusherTimeout(cfg.FlushTimeout),
		nats.RetryOnFailedConnect(true),

		// Standardized Connection Event Handlers
		nats.ClosedHandler(func(nc *nats.Conn) {
			log.Error("[%s] NATS connection closed unexpectedly", cfg.ClientID)
		}),
		nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
			log.Warning("[%s] NATS disconnected, attempting reconnect: %v", cfg.ClientID, err)
		}),
		nats.ReconnectHandler(func(nc *nats.Conn) {
			log.Info("[%s] NATS successfully reconnected to %s", cfg.ClientID, nc.ConnectedUrl())
		}),
	}

	// Wire Encryption / TLS configuration (for remote nodes or when explicitly configured)
	hasTLSScheme := false
	for _, s := range cfg.Servers {
		if strings.HasPrefix(strings.ToLower(s), "tls://") {
			hasTLSScheme = true
			break
		}
	}

	if (cfg.TLS != nil && cfg.TLS.Enabled) || hasTLSScheme {
		if cfg.TLS != nil {
			if cfg.TLS.CAFile != "" {
				opts = append(opts, nats.RootCAs(cfg.TLS.CAFile))
			}
			if cfg.TLS.CertFile != "" && cfg.TLS.KeyFile != "" {
				opts = append(opts, nats.ClientCert(cfg.TLS.CertFile, cfg.TLS.KeyFile))
			}
			if cfg.TLS.InsecureSkipVerify {
				opts = append(opts, nats.Secure(&tls.Config{InsecureSkipVerify: true}))
			} else if cfg.TLS.CAFile == "" && (cfg.TLS.CertFile == "" || cfg.TLS.KeyFile == "") {
				opts = append(opts, nats.Secure(nil))
			}
		} else {
			opts = append(opts, nats.Secure(nil))
		}
	}

	conn, err := nats.Connect(cfg.Servers[0], opts...)
	if err != nil {
		return nil, fmt.Errorf("nats connection failed: %w", err)
	}

	log.Info("[%s] Successfully connected to NATS at %s", cfg.ClientID, conn.ConnectedUrl())
	return conn, nil
}
