// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit test suite for NATS messaging connector and TLS configuration.
//
// DATA FLOW:
// Test NatsConfig -> Connect -> Validation
//
// KEY PARAMETERS:
// - NatsConfig: Evaluates error handling and TLS parameter parsing.
// -----------------------------------------------------------------------------

package messaging

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestNatsConfig_TLSValidation(t *testing.T) {
	cfg := &NatsConfig{
		ClientID:       "test-client",
		Servers:        []string{},
		ConnectTimeout: 1 * time.Second,
		TLS: &TLSConfig{
			Enabled:            true,
			CertFile:           "/path/to/cert.pem",
			KeyFile:            "/path/to/key.pem",
			CAFile:             "/path/to/ca.pem",
			InsecureSkipVerify: true,
		},
	}

	// Should error out when no servers configured without panicking on TLS setup
	conn, err := Connect(cfg, nil)
	assert.Error(t, err)
	assert.Nil(t, conn)
	assert.Contains(t, err.Error(), "no nats servers configured")
}

func TestNatsConfig_TLSSchemeDetection(t *testing.T) {
	cfg := &NatsConfig{
		ClientID:       "test-client",
		Servers:        []string{"tls://127.0.0.1:4222"},
		ConnectTimeout: 100 * time.Millisecond,
	}

	// Proves option parsing activates TLS (Secure option set)
	conn, err := Connect(cfg, nil)
	assert.NoError(t, err)
	if assert.NotNil(t, conn) {
		defer conn.Close()
		assert.True(t, conn.Opts.Secure, "Connection options must have Secure: true for tls:// scheme")
	}
}
