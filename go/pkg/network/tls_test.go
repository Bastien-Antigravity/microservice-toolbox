// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Verifies cold-path X.509 TLS/mTLS builders, DynamicTransportCredentials handshake
// policy enforcement, and runtime policy hot-reload behavior.
//
// DATA FLOW:
// Ephemeral Fleet CA / Leaf Certs -> net.Pipe + DynamicTransportCredentials -> Assertions
//
// KEY PARAMETERS:
// - ca.crt / ca.key: Test Fleet Root CA generated in t.TempDir().
// - tele-remote.crt / client.crt: Leaf server and client X.509 certificates.
// -----------------------------------------------------------------------------

package network

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"io"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type testPKI struct {
	CAFile            string
	CAKeyFile         string
	ServerCertFile    string
	ServerKeyFile     string
	ClientCertFile    string
	ClientKeyFile     string
	UntrustedCAFile   string
	UntrustedCertFile string
	UntrustedKeyFile  string
}

func generateTestPKI(t *testing.T) testPKI {
	t.Helper()
	dir := t.TempDir()

	caCert, caKey, caFile, caKeyFile := writeTestCA(t, dir, "ca", "Fleet Test Root CA")
	srvCertFile, srvKeyFile := writeSignedLeaf(t, dir, "tele-remote", caCert, caKey, "tele-remote",
		[]string{"localhost", "tele-remote"},
		[]net.IP{net.ParseIP("127.0.0.1"), net.ParseIP("192.168.1.50")},
		[]x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	)
	cliCertFile, cliKeyFile := writeSignedLeaf(t, dir, "client", caCert, caKey, "fleet-client",
		[]string{"fleet-client"},
		nil,
		[]x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	)

	untrustedCACert, untrustedCAKey, untrustedCAFile, _ := writeTestCA(t, dir, "untrusted-ca", "Untrusted CA")
	untrustedCertFile, untrustedKeyFile := writeSignedLeaf(t, dir, "untrusted-client", untrustedCACert, untrustedCAKey, "rogue-client",
		[]string{"rogue-client"},
		nil,
		[]x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	)

	return testPKI{
		CAFile:            caFile,
		CAKeyFile:         caKeyFile,
		ServerCertFile:    srvCertFile,
		ServerKeyFile:     srvKeyFile,
		ClientCertFile:    cliCertFile,
		ClientKeyFile:     cliKeyFile,
		UntrustedCAFile:   untrustedCAFile,
		UntrustedCertFile: untrustedCertFile,
		UntrustedKeyFile:  untrustedKeyFile,
	}
}

func writeTestCA(t *testing.T, dir, prefix, cn string) (*x509.Certificate, *ecdsa.PrivateKey, string, string) {
	t.Helper()
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)

	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 62))
	require.NoError(t, err)

	tmpl := &x509.Certificate{
		SerialNumber:          serial,
		Subject:               pkix.Name{CommonName: cn},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}

	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &priv.PublicKey, priv)
	require.NoError(t, err)

	cert, err := x509.ParseCertificate(der)
	require.NoError(t, err)

	certPath := filepath.Join(dir, prefix+".crt")
	keyPath := filepath.Join(dir, prefix+".key")
	writeCertAndKeyPEM(t, certPath, keyPath, der, priv)
	return cert, priv, certPath, keyPath
}

func writeSignedLeaf(
	t *testing.T,
	dir, prefix string,
	caCert *x509.Certificate,
	caKey *ecdsa.PrivateKey,
	cn string,
	dnsNames []string,
	ips []net.IP,
	extUsage []x509.ExtKeyUsage,
) (string, string) {
	t.Helper()
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)

	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 62))
	require.NoError(t, err)

	tmpl := &x509.Certificate{
		SerialNumber:          serial,
		Subject:               pkix.Name{CommonName: cn},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:           extUsage,
		BasicConstraintsValid: true,
		DNSNames:              dnsNames,
		IPAddresses:           ips,
	}

	der, err := x509.CreateCertificate(rand.Reader, tmpl, caCert, &priv.PublicKey, caKey)
	require.NoError(t, err)

	certPath := filepath.Join(dir, prefix+".crt")
	keyPath := filepath.Join(dir, prefix+".key")
	writeCertAndKeyPEM(t, certPath, keyPath, der, priv)
	return certPath, keyPath
}

func writeCertAndKeyPEM(t *testing.T, certPath, keyPath string, der []byte, priv *ecdsa.PrivateKey) {
	t.Helper()
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	require.NoError(t, os.WriteFile(certPath, certPEM, 0644))

	keyDER, err := x509.MarshalECPrivateKey(priv)
	require.NoError(t, err)
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER})
	require.NoError(t, os.WriteFile(keyPath, keyPEM, 0600))
}

type spoofedAddrConn struct {
	net.Conn
	remote net.Addr
}

func (c *spoofedAddrConn) RemoteAddr() net.Addr {
	return c.remote
}

func pipeWithRemoteIP(remoteIP string) (net.Conn, net.Conn) {
	serverConn, clientConn := net.Pipe()
	_ = serverConn.SetDeadline(time.Now().Add(5 * time.Second))
	_ = clientConn.SetDeadline(time.Now().Add(5 * time.Second))
	return &spoofedAddrConn{
		Conn:   serverConn,
		remote: &net.TCPAddr{IP: net.ParseIP(remoteIP), Port: 44444},
	}, clientConn
}

func TestDynamicTransportCredentials_ColdBootFailFast(t *testing.T) {
	t.Run("fails fast when TLS enabled without certs", func(t *testing.T) {
		creds, err := NewDynamicTransportCredentials("0.0.0.0", TLSPolicy{
			Enabled: true,
			Mode:    "auto",
		})
		assert.Error(t, err)
		assert.Nil(t, creds)
	})

	t.Run("fails fast when cert files do not exist", func(t *testing.T) {
		creds, err := NewDynamicTransportCredentials("0.0.0.0", TLSPolicy{
			Enabled: true,
			Mode:    "strict",
			LocalTLS: config.LocalTLSConfig{
				CertFile: "/nonexistent/server.crt",
				KeyFile:  "/nonexistent/server.key",
			},
		})
		assert.Error(t, err)
		assert.Nil(t, creds)
	})

	t.Run("boots cleanly over cleartext when disabled and no certs configured", func(t *testing.T) {
		creds, err := NewDynamicTransportCredentials("127.0.0.1", TLSPolicy{
			Enabled: false,
			Mode:    "auto",
		})
		require.NoError(t, err)
		require.NotNil(t, creds)
		assert.Equal(t, "insecure", creds.Info().SecurityProtocol)
	})
}

func TestDynamicTransportCredentials_AutoModeAndMTLS(t *testing.T) {
	pki := generateTestPKI(t)

	creds, err := NewDynamicTransportCredentials("127.0.0.1", TLSPolicy{
		Enabled: true,
		Mode:    "auto",
		LocalTLS: config.LocalTLSConfig{
			CertFile: pki.ServerCertFile,
			KeyFile:  pki.ServerKeyFile,
			CAFile:   pki.CAFile,
		},
	})
	require.NoError(t, err)
	assert.Equal(t, "tls", creds.Info().SecurityProtocol)

	t.Run("local cleartext allowed in auto mode", func(t *testing.T) {
		srvRaw, cliRaw := pipeWithRemoteIP("127.0.0.1")
		defer func() { _ = srvRaw.Close(); _ = cliRaw.Close() }()

		errCh := make(chan error, 1)
		go func() {
			_, err := cliRaw.Write([]byte("PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"))
			errCh <- err
		}()

		conn, authInfo, err := creds.ServerHandshake(srvRaw)
		require.NoError(t, err)
		require.NotNil(t, conn)
		assert.Equal(t, "insecure", authInfo.AuthType())

		buf := make([]byte, 24)
		_, err = io.ReadFull(conn, buf)
		require.NoError(t, err)
		assert.Equal(t, "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n", string(buf))
		require.NoError(t, <-errCh)
	})

	t.Run("remote cleartext rejected in auto mode", func(t *testing.T) {
		srvRaw, cliRaw := pipeWithRemoteIP("192.168.1.50")
		defer func() { _ = srvRaw.Close(); _ = cliRaw.Close() }()

		go func() {
			_, _ = cliRaw.Write([]byte("PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"))
		}()

		conn, _, err := creds.ServerHandshake(srvRaw)
		require.Error(t, err)
		assert.Nil(t, conn)
		assert.Contains(t, err.Error(), "⛔ Unauthorized access")
	})

	t.Run("remote mTLS with valid CA-signed client cert succeeds", func(t *testing.T) {
		clientTLS, err := BuildClientTLSConfig(config.LocalTLSConfig{
			CertFile: pki.ClientCertFile,
			KeyFile:  pki.ClientKeyFile,
			CAFile:   pki.CAFile,
		}, "192.168.1.50")
		require.NoError(t, err)

		srvRaw, cliRaw := pipeWithRemoteIP("192.168.1.50")
		defer func() { _ = srvRaw.Close(); _ = cliRaw.Close() }()

		cliErrCh := make(chan error, 1)
		go func() {
			tlsCli := tls.Client(cliRaw, clientTLS)
			if err := tlsCli.Handshake(); err != nil {
				cliErrCh <- err
				return
			}
			_, err := tlsCli.Write([]byte("ping"))
			cliErrCh <- err
		}()

		srvConn, authInfo, err := creds.ServerHandshake(srvRaw)
		require.NoError(t, err)
		require.NotNil(t, srvConn)
		assert.Equal(t, "tls", authInfo.AuthType())

		msg := make([]byte, 4)
		_, err = io.ReadFull(srvConn, msg)
		require.NoError(t, err)
		assert.Equal(t, "ping", string(msg))
		require.NoError(t, <-cliErrCh)
	})

	t.Run("remote TLS without client cert rejected by mTLS", func(t *testing.T) {
		clientTLS, err := BuildClientTLSConfig(config.LocalTLSConfig{
			CAFile: pki.CAFile,
		}, "192.168.1.50")
		require.NoError(t, err)

		srvRaw, cliRaw := pipeWithRemoteIP("192.168.1.50")
		defer func() { _ = srvRaw.Close(); _ = cliRaw.Close() }()

		go func() {
			tlsCli := tls.Client(cliRaw, clientTLS)
			if err := tlsCli.Handshake(); err == nil {
				_, _ = tlsCli.Read(make([]byte, 1))
			}
		}()

		srvConn, _, err := creds.ServerHandshake(srvRaw)
		require.Error(t, err)
		assert.Nil(t, srvConn)
		assert.Contains(t, err.Error(), "⛔ Unauthorized access")
	})

	t.Run("remote TLS with untrusted CA client cert rejected by mTLS", func(t *testing.T) {
		clientTLS, err := BuildClientTLSConfig(config.LocalTLSConfig{
			CertFile: pki.UntrustedCertFile,
			KeyFile:  pki.UntrustedKeyFile,
			CAFile:   pki.CAFile,
		}, "192.168.1.50")
		require.NoError(t, err)

		srvRaw, cliRaw := pipeWithRemoteIP("192.168.1.50")
		defer func() { _ = srvRaw.Close(); _ = cliRaw.Close() }()

		go func() {
			tlsCli := tls.Client(cliRaw, clientTLS)
			if err := tlsCli.Handshake(); err == nil {
				_, _ = tlsCli.Read(make([]byte, 1))
			}
		}()

		srvConn, _, err := creds.ServerHandshake(srvRaw)
		require.Error(t, err)
		assert.Nil(t, srvConn)
		assert.Contains(t, err.Error(), "⛔ Unauthorized access")
	})
}

func TestDynamicTransportCredentials_UpdatePolicyHotReload(t *testing.T) {
	pki := generateTestPKI(t)

	initialLocalTLS := config.LocalTLSConfig{
		CertFile: pki.ServerCertFile,
		KeyFile:  pki.ServerKeyFile,
		CAFile:   pki.CAFile,
	}

	creds, err := NewDynamicTransportCredentials("127.0.0.1", TLSPolicy{
		Enabled:  true,
		Mode:     "auto",
		LocalTLS: initialLocalTLS,
	})
	require.NoError(t, err)

	// 1. Switch auto -> strict: local cleartext is now rejected.
	require.NoError(t, creds.UpdatePolicy(TLSPolicy{
		Enabled:  true,
		Mode:     "strict",
		LocalTLS: initialLocalTLS,
	}))

	srvRaw1, cliRaw1 := pipeWithRemoteIP("127.0.0.1")
	go func() { _, _ = cliRaw1.Write([]byte("PRI * HTTP/2.0")) }()
	_, _, err = creds.ServerHandshake(srvRaw1)
	_ = srvRaw1.Close()
	_ = cliRaw1.Close()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "⛔ Unauthorized access: strict TLS required")

	// 2. Invalid cert path in UpdatePolicy returns error AND preserves previous strict TLS config.
	err = creds.UpdatePolicy(TLSPolicy{
		Enabled: true,
		Mode:    "auto",
		LocalTLS: config.LocalTLSConfig{
			CertFile: "/nonexistent/bad.crt",
			KeyFile:  "/nonexistent/bad.key",
		},
	})
	require.Error(t, err)

	// Verify previous strict policy is still intact!
	srvRaw2, cliRaw2 := pipeWithRemoteIP("127.0.0.1")
	go func() { _, _ = cliRaw2.Write([]byte("PRI * HTTP/2.0")) }()
	_, _, err = creds.ServerHandshake(srvRaw2)
	_ = srvRaw2.Close()
	_ = cliRaw2.Close()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "⛔ Unauthorized access: strict TLS required")

	// 3. Switch to disabled: cleartext (even remote) is now allowed.
	require.NoError(t, creds.UpdatePolicy(TLSPolicy{
		Enabled: false,
		Mode:    "disabled",
	}))
	assert.Equal(t, "insecure", creds.Info().SecurityProtocol)

	srvRaw3, cliRaw3 := pipeWithRemoteIP("192.168.1.50")
	defer func() { _ = srvRaw3.Close(); _ = cliRaw3.Close() }()
	go func() { _, _ = cliRaw3.Write([]byte("PRI *")) }()

	conn, authInfo, err := creds.ServerHandshake(srvRaw3)
	require.NoError(t, err)
	require.NotNil(t, conn)
	assert.Equal(t, "insecure", authInfo.AuthType())
}

func TestDialTransportCredentials(t *testing.T) {
	pki := generateTestPKI(t)
	localTLS := config.LocalTLSConfig{
		CertFile: pki.ClientCertFile,
		KeyFile:  pki.ClientKeyFile,
		CAFile:   pki.CAFile,
	}

	t.Run("local target with auto uses insecure", func(t *testing.T) {
		creds, err := DialTransportCredentials(localTLS, "127.0.0.1", true, "auto")
		require.NoError(t, err)
		assert.Equal(t, "insecure", creds.Info().SecurityProtocol)
	})

	t.Run("remote target with auto and enabled uses tls", func(t *testing.T) {
		creds, err := DialTransportCredentials(localTLS, "192.168.1.50", true, "auto")
		require.NoError(t, err)
		assert.Equal(t, "tls", creds.Info().SecurityProtocol)
	})

	t.Run("local target with strict uses tls", func(t *testing.T) {
		creds, err := DialTransportCredentials(localTLS, "127.0.0.1", false, "strict")
		require.NoError(t, err)
		assert.Equal(t, "tls", creds.Info().SecurityProtocol)
	})

	t.Run("remote target with disabled uses insecure", func(t *testing.T) {
		creds, err := DialTransportCredentials(localTLS, "192.168.1.50", true, "disabled")
		require.NoError(t, err)
		assert.Equal(t, "insecure", creds.Info().SecurityProtocol)
	})

	t.Run("remote target with remote_only uses tls even when tlsEnabled is false", func(t *testing.T) {
		creds, err := DialTransportCredentials(localTLS, "192.168.1.50", false, "remote_only")
		require.NoError(t, err)
		assert.Equal(t, "tls", creds.Info().SecurityProtocol)
	})

	t.Run("strict fails fast when CA missing", func(t *testing.T) {
		creds, err := DialTransportCredentials(config.LocalTLSConfig{}, "127.0.0.1", true, "strict")
		assert.Error(t, err)
		assert.Nil(t, creds)
	})
}
