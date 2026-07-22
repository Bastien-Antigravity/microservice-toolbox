package messaging

import (
	"fmt"

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

	conn, err := nats.Connect(cfg.Servers[0], opts...)
	if err != nil {
		return nil, fmt.Errorf("nats connection failed: %w", err)
	}

	log.Info("[%s] Successfully connected to NATS at %s", cfg.ClientID, conn.ConnectedUrl())
	return conn, nil
}
