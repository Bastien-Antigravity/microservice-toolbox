// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Provides reusable X.509 TLS/mTLS client configuration builders and local/remote
// policy helpers for tonic gRPC endpoints.
//
// DATA FLOW:
// LocalTLSConfig + TLS Policy -> build_client_tls_config / build_client_endpoint -> tonic Endpoint
//
// KEY PARAMETERS:
// - local_tls: Service-private X.509 cert_file, key_file, ca_file, and verify_client.
// - tls_mode: Enforcement policy ("auto", "local_plaintext", "remote_only", "strict", "disabled").
// -----------------------------------------------------------------------------

use std::net::IpAddr;

use tonic::transport::{Certificate, ClientTlsConfig, Endpoint, Identity};

use crate::config::LocalTLSConfig;

//-----------------------------------------------------------------------------------------------
// Policy & Locality Helpers
//-----------------------------------------------------------------------------------------------

/// Canonicalizes a TLS policy mode string, defaulting empty values to "auto".
pub fn normalize_tls_mode(mode: &str) -> String {
    let normalized = mode.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        "auto".to_string()
    } else {
        normalized
    }
}

/// Reports whether host represents a loopback or localhost address.
pub fn is_local_address(host: &str) -> bool {
    let h = host.trim().trim_matches(&['[', ']'][..]).trim();
    if h.is_empty() {
        return false;
    }
    if h.eq_ignore_ascii_case("localhost") {
        return true;
    }
    if let Ok(ip) = h.parse::<IpAddr>() {
        return ip.is_loopback();
    }
    false
}

/// Extracts the bare host portion from an optional host:port or [ipv6]:port target string.
fn extract_host(target_ip: &str) -> &str {
    let raw = target_ip.trim();
    if raw.is_empty() {
        return "";
    }
    if raw.starts_with('[') {
        if let Some(end_bracket) = raw.find(']') {
            return &raw[1..end_bracket];
        }
        return raw.trim_matches(&['[', ']'][..]);
    }
    if raw.parse::<IpAddr>().is_ok() {
        return raw;
    }
    if let Some((host, port_part)) = raw.rsplit_once(':')
        && !host.contains(':')
        && !port_part.is_empty()
        && port_part.chars().all(|c| c.is_ascii_digit())
    {
        return host;
    }
    raw
}

/// Determines whether a client connection to target_ip should use TLS under the active policy.
pub fn should_use_client_tls(target_ip: &str, tls_enabled: bool, tls_mode: &str) -> bool {
    let mode = normalize_tls_mode(tls_mode);
    let host = extract_host(target_ip);
    match mode.as_str() {
        "disabled" => false,
        "strict" | "required" => true,
        _ => (tls_enabled || mode == "remote_only") && !is_local_address(host),
    }
}

//-----------------------------------------------------------------------------------------------
// Cold-Path TLS Builders
//-----------------------------------------------------------------------------------------------

/// Loads and validates X.509 client TLS/mTLS credentials on the cold path.
pub fn build_client_tls_config(local_tls: &LocalTLSConfig, server_name: &str) -> Result<ClientTlsConfig, String> {
    let ca_file = local_tls.ca_file.trim();
    let cert_file = local_tls.cert_file.trim();
    let key_file = local_tls.key_file.trim();

    if ca_file.is_empty() {
        return Err("TLS client config requires ca_file".to_string());
    }

    let ca_pem = std::fs::read(ca_file)
        .map_err(|e| format!("failed to read TLS CA file {}: {}", ca_file, e))?;

    let trimmed_server_name = server_name.trim();
    let resolved_server_name = if trimmed_server_name.is_empty() {
        "localhost"
    } else {
        trimmed_server_name
    };

    let mut tls_cfg = ClientTlsConfig::new()
        .ca_certificate(Certificate::from_pem(ca_pem))
        .domain_name(resolved_server_name.to_string());

    if !cert_file.is_empty() || !key_file.is_empty() {
        if cert_file.is_empty() || key_file.is_empty() {
            return Err("TLS client mTLS identity requires both cert_file and key_file".to_string());
        }
        let cert_pem = std::fs::read(cert_file)
            .map_err(|e| format!("failed to read TLS client cert file {}: {}", cert_file, e))?;
        let key_pem = std::fs::read(key_file)
            .map_err(|e| format!("failed to read TLS client key file {}: {}", key_file, e))?;
        tls_cfg = tls_cfg.identity(Identity::from_pem(cert_pem, key_pem));
    }

    Ok(tls_cfg)
}

/// Builds a tonic transport Endpoint with TLS/mTLS or plaintext according to target locality and policy.
pub fn build_client_endpoint(
    target_ip: &str,
    target_port: i32,
    local_tls: &LocalTLSConfig,
    tls_enabled: bool,
    tls_mode: &str,
) -> Result<Endpoint, String> {
    let host = extract_host(target_ip);
    if host.is_empty() {
        return Err("target_ip cannot be empty".to_string());
    }

    let formatted_host = if host.contains(':') {
        format!("[{}]", host)
    } else {
        host.to_string()
    };

    if should_use_client_tls(target_ip, tls_enabled, tls_mode) {
        let tls_cfg = build_client_tls_config(local_tls, host)?;
        let uri = format!("https://{}:{}", formatted_host, target_port);
        let endpoint = Endpoint::from_shared(uri.clone())
            .map_err(|e| format!("invalid TLS endpoint {}: {}", uri, e))?;
        endpoint
            .tls_config(tls_cfg)
            .map_err(|e| format!("failed to apply TLS config for {}: {}", uri, e))
    } else {
        let uri = format!("http://{}:{}", formatted_host, target_port);
        Endpoint::from_shared(uri.clone())
            .map_err(|e| format!("invalid plaintext endpoint {}: {}", uri, e))
    }
}

//-----------------------------------------------------------------------------------------------
// Unit Tests
//-----------------------------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::{Path, PathBuf};
    use std::process::Command;

    struct TempTlsDir(PathBuf);

    impl TempTlsDir {
        fn new(suffix: &str) -> Self {
            let unique = format!(
                "rust_toolbox_tls_{}_{}",
                suffix,
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            );
            let dir = std::env::temp_dir().join(unique);
            std::fs::create_dir_all(&dir).unwrap();
            Self(dir)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TempTlsDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn generate_test_certs(dir: &Path, service: &str) {
        let tool = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../distributed-config/bin/config-tool");
        if tool.is_file() {
            let ca_status = Command::new(&tool)
                .args(["tlsgen", "--dir", &dir.to_string_lossy(), "--ca"])
                .status()
                .expect("failed to execute config-tool tlsgen --ca");
            assert!(ca_status.success(), "config-tool tlsgen --ca failed");

            let svc_status = Command::new(&tool)
                .args([
                    "tlsgen",
                    "--dir",
                    &dir.to_string_lossy(),
                    "--service",
                    service,
                    "--hosts",
                    "127.0.0.1,localhost",
                ])
                .status()
                .expect("failed to execute config-tool tlsgen --service");
            assert!(svc_status.success(), "config-tool tlsgen --service failed");
            return;
        }

        // Zone-1 standalone fallback when sibling distributed-config binary is absent
        let ca_key = dir.join("ca.key");
        let ca_crt = dir.join("ca.crt");
        let svc_key = dir.join(format!("{}.key", service));
        let svc_csr = dir.join(format!("{}.csr", service));
        let svc_crt = dir.join(format!("{}.crt", service));
        let svc_ext = dir.join(format!("{}.ext", service));
        std::fs::write(&svc_ext, "subjectAltName=IP:127.0.0.1,DNS:localhost\n")
            .expect("failed to write test openssl extfile");

        let ca_status = Command::new("openssl")
            .args([
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                &ca_key.to_string_lossy(),
                "-out",
                &ca_crt.to_string_lossy(),
                "-days",
                "1",
                "-subj",
                "/CN=bastien-test-ca",
            ])
            .status()
            .expect("failed to execute openssl ca generation");
        assert!(ca_status.success(), "openssl ca generation failed");

        let csr_subj = format!("/CN={}", service);
        let csr_status = Command::new("openssl")
            .args([
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                &svc_key.to_string_lossy(),
                "-out",
                &svc_csr.to_string_lossy(),
                "-subj",
                &csr_subj,
            ])
            .status()
            .expect("failed to execute openssl csr generation");
        assert!(csr_status.success(), "openssl csr generation failed");

        let sign_status = Command::new("openssl")
            .args([
                "x509",
                "-req",
                "-in",
                &svc_csr.to_string_lossy(),
                "-CA",
                &ca_crt.to_string_lossy(),
                "-CAkey",
                &ca_key.to_string_lossy(),
                "-CAcreateserial",
                "-out",
                &svc_crt.to_string_lossy(),
                "-days",
                "1",
                "-extfile",
                &svc_ext.to_string_lossy(),
            ])
            .status()
            .expect("failed to execute openssl x509 signing");
        assert!(sign_status.success(), "openssl x509 signing failed");
    }

    #[test]
    fn test_normalize_tls_mode() {
        assert_eq!(normalize_tls_mode(""), "auto");
        assert_eq!(normalize_tls_mode("   "), "auto");
        assert_eq!(normalize_tls_mode("  STRICT "), "strict");
        assert_eq!(normalize_tls_mode("Remote_Only"), "remote_only");
        assert_eq!(normalize_tls_mode("disabled"), "disabled");
    }

    #[test]
    fn test_is_local_address() {
        assert!(is_local_address("localhost"));
        assert!(is_local_address(" LOCALHOST "));
        assert!(is_local_address("127.0.0.1"));
        assert!(is_local_address("::1"));
        assert!(is_local_address("[::1]"));
        assert!(!is_local_address("10.0.0.5"));
        assert!(!is_local_address("tele-remote.internal"));
        assert!(!is_local_address(""));
    }

    #[test]
    fn test_should_use_client_tls() {
        // disabled always false
        assert!(!should_use_client_tls("10.0.0.5", true, "disabled"));
        assert!(!should_use_client_tls("127.0.0.1", true, "disabled"));

        // strict / required always true (even on loopback)
        assert!(should_use_client_tls("127.0.0.1", false, "strict"));
        assert!(should_use_client_tls("localhost:50051", false, "required"));
        assert!(should_use_client_tls("[::1]:50051", false, "strict"));

        // auto / local_plaintext: plaintext on loopback, TLS on remote when enabled
        assert!(!should_use_client_tls("127.0.0.1", true, "auto"));
        assert!(!should_use_client_tls("localhost:50051", true, ""));
        assert!(!should_use_client_tls("[::1]:50051", true, "local_plaintext"));
        assert!(!should_use_client_tls("::1", true, "auto"));
        assert!(should_use_client_tls("10.0.0.5:50051", true, "auto"));
        assert!(!should_use_client_tls("10.0.0.5", false, "auto"));

        // remote_only: TLS on remote even when tls_enabled=false, plaintext on loopback
        assert!(should_use_client_tls("10.0.0.5", false, "remote_only"));
        assert!(should_use_client_tls("[2001:db8::1]:50051", false, "remote_only"));
        assert!(!should_use_client_tls("127.0.0.1", true, "remote_only"));
    }

    #[test]
    fn test_build_client_tls_config_validation_and_certs() {
        let tmp = TempTlsDir::new("client_cfg");
        generate_test_certs(tmp.path(), "tele_remote");

        let ca_file = tmp.path().join("ca.crt").to_string_lossy().to_string();
        let cert_file = tmp.path().join("tele_remote.crt").to_string_lossy().to_string();
        let key_file = tmp.path().join("tele_remote.key").to_string_lossy().to_string();

        // Missing CA fails fast
        let missing_ca = LocalTLSConfig::default();
        assert!(build_client_tls_config(&missing_ca, "localhost").is_err());

        // Non-existent CA path fails fast
        let bad_ca = LocalTLSConfig {
            ca_file: tmp.path().join("missing-ca.crt").to_string_lossy().to_string(),
            ..Default::default()
        };
        assert!(build_client_tls_config(&bad_ca, "localhost").is_err());

        // Half-configured mTLS (cert without key, key without cert) fails fast
        let cert_only = LocalTLSConfig {
            ca_file: ca_file.clone(),
            cert_file: cert_file.clone(),
            key_file: String::new(),
            verify_client: None,
        };
        assert!(build_client_tls_config(&cert_only, "127.0.0.1").is_err());

        let key_only = LocalTLSConfig {
            ca_file: ca_file.clone(),
            cert_file: String::new(),
            key_file: key_file.clone(),
            verify_client: None,
        };
        assert!(build_client_tls_config(&key_only, "127.0.0.1").is_err());

        // CA-only TLS succeeds
        let ca_only = LocalTLSConfig {
            ca_file: ca_file.clone(),
            ..Default::default()
        };
        assert!(build_client_tls_config(&ca_only, "").is_ok());

        // Full mTLS succeeds
        let mtls = LocalTLSConfig {
            ca_file,
            cert_file,
            key_file,
            verify_client: Some(true),
        };
        assert!(build_client_tls_config(&mtls, "127.0.0.1").is_ok());
    }

    #[test]
    fn test_build_client_endpoint_schemes() {
        let tmp = TempTlsDir::new("endpoint");
        generate_test_certs(tmp.path(), "tele_remote");

        let mtls = LocalTLSConfig {
            ca_file: tmp.path().join("ca.crt").to_string_lossy().to_string(),
            cert_file: tmp.path().join("tele_remote.crt").to_string_lossy().to_string(),
            key_file: tmp.path().join("tele_remote.key").to_string_lossy().to_string(),
            verify_client: None,
        };

        // Local loopback in auto mode -> http://
        let local_ep = build_client_endpoint("127.0.0.1", 50051, &mtls, true, "auto").unwrap();
        assert_eq!(local_ep.uri().scheme_str(), Some("http"));
        assert_eq!(local_ep.uri().authority().unwrap().as_str(), "127.0.0.1:50051");

        // Remote host in auto mode with tls_enabled -> https://
        let remote_ep = build_client_endpoint("10.10.0.8", 50051, &mtls, true, "auto").unwrap();
        assert_eq!(remote_ep.uri().scheme_str(), Some("https"));
        assert_eq!(remote_ep.uri().authority().unwrap().as_str(), "10.10.0.8:50051");

        // Local loopback in strict mode -> https://
        let strict_ep = build_client_endpoint("::1", 50051, &mtls, false, "strict").unwrap();
        assert_eq!(strict_ep.uri().scheme_str(), Some("https"));
        assert_eq!(strict_ep.uri().authority().unwrap().as_str(), "[::1]:50051");
    }
}
