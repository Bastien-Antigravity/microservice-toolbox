// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Provides reusable X.509 TLS/mTLS configuration builders and runtime-toggleable
// gRPC TransportCredentials with local/remote policy enforcement.
//
// DATA FLOW:
// LocalTLSConfig + TLSPolicy -> TLS Config / DynamicTransportCredentials -> gRPC Peer
//
// KEY PARAMETERS:
// - LocalTLS: Service-private X.509 cert_file, key_file, ca_file, and verify_client.
// - Mode: TLS enforcement policy ("auto", "local_plaintext", "remote_only", "strict", "disabled").
// -----------------------------------------------------------------------------

package network

import (
	"bufio"
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
)

// -----------------------------------------------------------------------------

// TLSPolicy describes runtime-toggleable, local/remote-aware gRPC TLS/mTLS settings.
type TLSPolicy struct {
	Enabled  bool
	Mode     string // "auto" (default), "local_plaintext", "remote_only", "strict" / "required", "disabled"
	LocalTLS config.LocalTLSConfig
}

// -----------------------------------------------------------------------------

// NormalizeTLSMode canonicalizes a TLS policy mode string, defaulting empty values to "auto".
func NormalizeTLSMode(mode string) string {
	normalized := strings.ToLower(strings.TrimSpace(mode))
	if normalized == "" {
		return "auto"
	}
	return normalized
}

// IsLocalAddress reports whether host represents a loopback or localhost address.
func IsLocalAddress(host string) bool {
	h := strings.TrimSpace(host)
	h = strings.Trim(h, "[]")
	if h == "" {
		return false
	}
	if strings.EqualFold(h, "localhost") {
		return true
	}
	if ip := net.ParseIP(h); ip != nil && ip.IsLoopback() {
		return true
	}
	return false
}

// IsLocalPeerAddr reports whether a peer net.Addr originates from loopback or matches bindIP.
func IsLocalPeerAddr(addr net.Addr, bindIP string) bool {
	if addr == nil {
		return false
	}
	raw := strings.TrimSpace(addr.String())
	if raw == "" {
		return false
	}
	host, _, err := net.SplitHostPort(raw)
	if err != nil {
		host = raw
	}
	if IsLocalAddress(host) {
		return true
	}
	trimmedBind := strings.TrimSpace(bindIP)
	return trimmedBind != "" && host == trimmedBind
}

// -----------------------------------------------------------------------------

// BuildServerTLSConfig loads and validates X.509 server TLS/mTLS credentials on the cold path.
func BuildServerTLSConfig(localTLS config.LocalTLSConfig) (*tls.Config, error) {
	certFile := strings.TrimSpace(localTLS.CertFile)
	keyFile := strings.TrimSpace(localTLS.KeyFile)
	caFile := strings.TrimSpace(localTLS.CAFile)

	if certFile == "" || keyFile == "" {
		return nil, fmt.Errorf("TLS server config requires both cert_file and key_file")
	}

	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, fmt.Errorf("failed to load server TLS keypair (%s, %s): %w", certFile, keyFile, err)
	}

	tlsCfg := &tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS12,
		NextProtos:   []string{"h2"},
	}

	if caFile != "" && localTLS.ShouldVerifyClient() {
		caPool, err := loadCACertPool(caFile)
		if err != nil {
			return nil, err
		}
		tlsCfg.ClientCAs = caPool
		tlsCfg.ClientAuth = tls.RequireAndVerifyClientCert
	}

	return tlsCfg, nil
}

// BuildClientTLSConfig loads and validates X.509 client TLS/mTLS credentials on the cold path.
func BuildClientTLSConfig(localTLS config.LocalTLSConfig, serverName string) (*tls.Config, error) {
	caFile := strings.TrimSpace(localTLS.CAFile)
	certFile := strings.TrimSpace(localTLS.CertFile)
	keyFile := strings.TrimSpace(localTLS.KeyFile)

	if caFile == "" {
		return nil, fmt.Errorf("TLS client config requires ca_file")
	}

	caPool, err := loadCACertPool(caFile)
	if err != nil {
		return nil, err
	}

	resolvedServerName := strings.TrimSpace(serverName)
	if resolvedServerName == "" {
		resolvedServerName = "localhost"
	}

	tlsCfg := &tls.Config{
		RootCAs:    caPool,
		MinVersion: tls.VersionTLS12,
		NextProtos: []string{"h2"},
		ServerName: resolvedServerName,
	}

	if certFile != "" || keyFile != "" {
		if certFile == "" || keyFile == "" {
			return nil, fmt.Errorf("TLS client mTLS identity requires both cert_file and key_file")
		}
		cert, err := tls.LoadX509KeyPair(certFile, keyFile)
		if err != nil {
			return nil, fmt.Errorf("failed to load client TLS keypair (%s, %s): %w", certFile, keyFile, err)
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
	}

	return tlsCfg, nil
}

func loadCACertPool(caFile string) (*x509.CertPool, error) {
	caPEM, err := os.ReadFile(caFile)
	if err != nil {
		return nil, fmt.Errorf("failed to read TLS CA file %s: %w", caFile, err)
	}
	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("failed to parse TLS CA PEM %s", caFile)
	}
	return caPool, nil
}

// DialTransportCredentials builds gRPC client TransportCredentials according to target locality and policy.
func DialTransportCredentials(localTLS config.LocalTLSConfig, targetIP string, tlsEnabled bool, tlsMode string) (credentials.TransportCredentials, error) {
	mode := NormalizeTLSMode(tlsMode)
	host := strings.TrimSpace(targetIP)
	if parsedHost, _, err := net.SplitHostPort(host); err == nil {
		host = parsedHost
	}

	switch mode {
	case "disabled":
		return insecure.NewCredentials(), nil
	case "strict", "required":
		tlsCfg, err := BuildClientTLSConfig(localTLS, host)
		if err != nil {
			return nil, err
		}
		return credentials.NewTLS(tlsCfg), nil
	default:
		if (tlsEnabled || mode == "remote_only") && !IsLocalAddress(host) {
			tlsCfg, err := BuildClientTLSConfig(localTLS, host)
			if err != nil {
				return nil, err
			}
			return credentials.NewTLS(tlsCfg), nil
		}
		return insecure.NewCredentials(), nil
	}
}

// -----------------------------------------------------------------------------

// DynamicTransportCredentials enforces runtime-toggleable TLS/mTLS vs local cleartext on a gRPC server.
type DynamicTransportCredentials struct {
	mu        sync.RWMutex
	bindIP    string
	policy    TLSPolicy
	tlsConfig *tls.Config
}

type peekedConn struct {
	net.Conn
	r *bufio.Reader
}

func (c *peekedConn) Read(p []byte) (int, error) {
	return c.r.Read(p)
}

type plaintextAuthInfo struct {
	credentials.CommonAuthInfo
}

func (plaintextAuthInfo) AuthType() string {
	return "insecure"
}

func shouldLoadServerTLS(policy TLSPolicy) bool {
	mode := NormalizeTLSMode(policy.Mode)
	if mode == "disabled" {
		return false
	}
	return policy.Enabled || mode == "strict" || mode == "required" || mode == "remote_only"
}

// NewDynamicTransportCredentials validates initial TLS policy and fails fast if required certs are missing or invalid.
func NewDynamicTransportCredentials(bindIP string, policy TLSPolicy) (*DynamicTransportCredentials, error) {
	policy.Mode = NormalizeTLSMode(policy.Mode)

	var tlsCfg *tls.Config
	if shouldLoadServerTLS(policy) {
		var err error
		tlsCfg, err = BuildServerTLSConfig(policy.LocalTLS)
		if err != nil {
			return nil, err
		}
	}

	return &DynamicTransportCredentials{
		bindIP:    strings.TrimSpace(bindIP),
		policy:    policy,
		tlsConfig: tlsCfg,
	}, nil
}

// UpdatePolicy validates and atomically swaps the active TLS policy without mutating state on failure.
func (d *DynamicTransportCredentials) UpdatePolicy(policy TLSPolicy) error {
	policy.Mode = NormalizeTLSMode(policy.Mode)

	var newTLSCfg *tls.Config
	if shouldLoadServerTLS(policy) {
		var err error
		newTLSCfg, err = BuildServerTLSConfig(policy.LocalTLS)
		if err != nil {
			return err
		}
	}

	d.mu.Lock()
	d.policy = policy
	d.tlsConfig = newTLSCfg
	d.mu.Unlock()
	return nil
}

// ServerHandshake inspects the first wire byte to enforce local/remote TLS/mTLS policy per connection.
func (d *DynamicTransportCredentials) ServerHandshake(rawConn net.Conn) (net.Conn, credentials.AuthInfo, error) {
	br := bufio.NewReader(rawConn)
	peekBytes, err := br.Peek(1)
	if err != nil {
		return nil, nil, err
	}

	isTLSClientHello := len(peekBytes) == 1 && peekBytes[0] == 0x16
	pConn := &peekedConn{Conn: rawConn, r: br}

	d.mu.RLock()
	policy := d.policy
	bindIP := d.bindIP
	tlsCfg := d.tlsConfig
	d.mu.RUnlock()

	remoteAddr := "<unknown>"
	if rawConn.RemoteAddr() != nil {
		remoteAddr = rawConn.RemoteAddr().String()
	}

	mode := NormalizeTLSMode(policy.Mode)
	switch {
	case mode == "disabled" || (!policy.Enabled && mode != "strict" && mode != "required" && mode != "remote_only"):
		if isTLSClientHello && tlsCfg != nil {
			return performServerTLSHandshake(pConn, tlsCfg)
		}
		if isTLSClientHello {
			return nil, nil, fmt.Errorf("TLS handshake attempted while server TLS is unconfigured (%s)", remoteAddr)
		}
		return pConn, plaintextAuthInfo{CommonAuthInfo: credentials.CommonAuthInfo{SecurityLevel: credentials.NoSecurity}}, nil

	case mode == "strict" || mode == "required":
		if !isTLSClientHello {
			return nil, nil, fmt.Errorf("⛔ Unauthorized access: strict TLS required (%s)", remoteAddr)
		}
		if tlsCfg == nil {
			return nil, nil, fmt.Errorf("⛔ Unauthorized access: strict TLS configured without server certificate (%s)", remoteAddr)
		}
		return performServerTLSHandshake(pConn, tlsCfg)

	default:
		if !IsLocalPeerAddr(rawConn.RemoteAddr(), bindIP) && !isTLSClientHello {
			return nil, nil, fmt.Errorf("⛔ Unauthorized access: TLS required for non-local microservice (%s)", remoteAddr)
		}
		if isTLSClientHello {
			if tlsCfg == nil {
				return nil, nil, fmt.Errorf("⛔ Unauthorized access: TLS handshake attempted without server certificate (%s)", remoteAddr)
			}
			return performServerTLSHandshake(pConn, tlsCfg)
		}
		return pConn, plaintextAuthInfo{CommonAuthInfo: credentials.CommonAuthInfo{SecurityLevel: credentials.NoSecurity}}, nil
	}
}

func performServerTLSHandshake(pConn net.Conn, tlsCfg *tls.Config) (net.Conn, credentials.AuthInfo, error) {
	tlsConn := tls.Server(pConn, tlsCfg)
	if err := tlsConn.Handshake(); err != nil {
		_ = tlsConn.Close()
		return nil, nil, fmt.Errorf("⛔ Unauthorized access: TLS handshake failed: %w", err)
	}
	authInfo := credentials.TLSInfo{
		State: tlsConn.ConnectionState(),
		CommonAuthInfo: credentials.CommonAuthInfo{
			SecurityLevel: credentials.PrivacyAndIntegrity,
		},
	}
	return tlsConn, authInfo, nil
}

// ClientHandshake is unsupported on server-side DynamicTransportCredentials.
func (d *DynamicTransportCredentials) ClientHandshake(_ context.Context, _ string, _ net.Conn) (net.Conn, credentials.AuthInfo, error) {
	return nil, nil, fmt.Errorf("DynamicTransportCredentials is server-side only; use DialTransportCredentials for client connections")
}

// Info returns the ProtocolInfo for the currently active credentials policy.
func (d *DynamicTransportCredentials) Info() credentials.ProtocolInfo {
	d.mu.RLock()
	hasTLS := d.tlsConfig != nil && NormalizeTLSMode(d.policy.Mode) != "disabled"
	d.mu.RUnlock()

	if hasTLS {
		return credentials.ProtocolInfo{
			SecurityProtocol: "tls",
			SecurityVersion:  "1.2",
		}
	}
	return credentials.ProtocolInfo{
		SecurityProtocol: "insecure",
	}
}

// Clone returns a copy of DynamicTransportCredentials sharing the active policy snapshot.
func (d *DynamicTransportCredentials) Clone() credentials.TransportCredentials {
	d.mu.RLock()
	defer d.mu.RUnlock()

	var clonedTLS *tls.Config
	if d.tlsConfig != nil {
		clonedTLS = d.tlsConfig.Clone()
	}
	return &DynamicTransportCredentials{
		bindIP:    d.bindIP,
		policy:    d.policy,
		tlsConfig: clonedTLS,
	}
}

// OverrideServerName is a no-op retained to satisfy credentials.TransportCredentials.
func (d *DynamicTransportCredentials) OverrideServerName(_ string) error {
	return nil
}
