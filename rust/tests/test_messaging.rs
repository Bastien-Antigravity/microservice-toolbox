// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Tests NATS messaging connector and TLS configuration in Rust.
//
// DATA FLOW:
// Test Config -> NatsConfig -> connect() -> Validation
//
// KEY PARAMETERS:
// - NatsConfig: Evaluates error handling and TLS configuration logic.
// -----------------------------------------------------------------------------

use microservice_toolbox::messaging::config::{NatsConfig, TlsConfig};
use microservice_toolbox::messaging::connector;

#[tokio::test]
async fn test_nats_empty_servers_fails() {
    let cfg = NatsConfig {
        servers: vec![],
        subject: "test".to_string(),
        cluster_id: "test-cluster".to_string(),
        client_id: "test-client".to_string(),
        connect_timeout_secs: 1,
        reconnect_wait_secs: 1,
        max_reconnects: 1,
        flush_timeout_secs: 1,
        subject_prefix: "bastien-antigravity".to_string(),
        jetstream: None,
        tls: None,
    };

    let result = connector::connect(&cfg, None).await;
    assert!(result.is_err());
    let err_str = result.err().unwrap().to_string();
    assert!(err_str.contains("no nats servers configured"));
}

#[tokio::test]
async fn test_nats_tls_config_structure() {
    let cfg = NatsConfig {
        servers: vec!["nats://127.0.0.1:4222".to_string()],
        subject: "test".to_string(),
        cluster_id: "test-cluster".to_string(),
        client_id: "test-client".to_string(),
        connect_timeout_secs: 1,
        reconnect_wait_secs: 1,
        max_reconnects: 1,
        flush_timeout_secs: 1,
        subject_prefix: "bastien-antigravity".to_string(),
        jetstream: None,
        tls: Some(TlsConfig {
            enabled: true,
            cert_file: Some("/path/to/cert.pem".to_string()),
            key_file: Some("/path/to/key.pem".to_string()),
            ca_file: Some("/path/to/ca.pem".to_string()),
            insecure_skip_verify: false,
        }),
    };

    assert!(cfg.tls.is_some());
    let tls = cfg.tls.unwrap();
    assert!(tls.enabled);
    assert_eq!(tls.cert_file.unwrap(), "/path/to/cert.pem");
    assert_eq!(tls.key_file.unwrap(), "/path/to/key.pem");
    assert_eq!(tls.ca_file.unwrap(), "/path/to/ca.pem");
}
