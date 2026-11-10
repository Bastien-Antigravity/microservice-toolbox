//! ESSENTIAL PROCESS:
//! Integration tests for Rust ServiceSpec dynamic validation, port extraction,
//! zero-fallback fail-fast verification, and web_interface registration.
//!
//! DATA FLOW:
//! 1. Valid ServiceSpec + Mock AppConfig -> build_spec_from_config -> Verify extracted endpoints & metadata
//! 2. Missing metadata fields -> build_spec_from_config -> Verify fail-fast Result error
//! 3. Missing web_interface -> publish_service_spec -> Verify fail-fast Result error
//!
//! KEY PARAMETERS:
//! - None (Unit Test Suite).

use microservice_toolbox::config::loader::AppConfig;
use microservice_toolbox::spec::{
    build_spec_from_config, publish_service_spec, publish_service_spec_sync, ContractOperation, ContractPeer,
    ExchangeContract, ServiceSpec,
};

//-----------------------------------------------------------------------------------------------
#[test]
fn test_build_spec_from_config_valid() {
    let yaml_str = r#"
capabilities:
  config_server:
    ip: "127.0.0.1"
    port: "3306"
    rest_port: "3308"
    grpc_port: "3307"
"#;
    let data: serde_yml::Value = serde_yml::from_str(yaml_str).expect("yaml deserialization failed");
    let app_config = AppConfig::from_value(data);

    let base = ServiceSpec {
        name: "Config Server".to_string(),
        tag: "config-server-mfe".to_string(),
        layer: "L1".to_string(),
        category: "Base Fleet".to_string(),
        priority: 20,
        icon: "fa-cogs".to_string(),
        description: "Centralized configuration repository.".to_string(),
        doc_link: "obsidian-brain/06-Microservices/Config-Server-Hub.md".to_string(),
        protocol: "TCP, REST & gRPC".to_string(),
        framing: "Port %s TCP / Port %s REST".to_string(),
        ..Default::default()
    };

    let spec = build_spec_from_config(&app_config, "config_server", base).expect("build_spec_from_config failed");
    assert_eq!(spec.name, "Config Server");
    assert_eq!(spec.capability, "config_server");
    assert_eq!(spec.layer, "L1");
    assert_eq!(spec.category, "Base Fleet");
    assert!(spec.framing.contains("3306"));
    assert!(spec.framing.contains("3308"));
    assert_eq!(spec.doc_link, "obsidian-brain/06-Microservices/Config-Server-Hub.md");
    assert!(spec.data_structure.get("version").is_some());
    assert_eq!(spec.url, "http://127.0.0.1:3308");
}

//-----------------------------------------------------------------------------------------------
#[test]
fn test_build_spec_from_config_fail_fast() {
    let yaml_str = r#"
capabilities:
  config_server:
    ip: "127.0.0.1"
    port: "3306"
"#;
    let data: serde_yml::Value = serde_yml::from_str(yaml_str).expect("yaml deserialization failed");
    let app_config = AppConfig::from_value(data);

    let valid_base = ServiceSpec {
        name: "Config Server".to_string(),
        tag: "config-server-mfe".to_string(),
        layer: "L1".to_string(),
        category: "Base Fleet".to_string(),
        description: "Centralized configuration repository.".to_string(),
        doc_link: "obsidian-brain/06-Microservices/Config-Server-Hub.md".to_string(),
        protocol: "TCP".to_string(),
        framing: "Port %s TCP".to_string(),
        ..Default::default()
    };

    // 1. empty capability
    assert!(build_spec_from_config(&app_config, "", valid_base.clone()).is_err());

    // 2. missing name
    let mut b = valid_base.clone();
    b.name = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 3. missing layer
    let mut b = valid_base.clone();
    b.layer = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 4. missing category
    let mut b = valid_base.clone();
    b.category = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 5. missing description
    let mut b = valid_base.clone();
    b.description = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 6. missing doc_link
    let mut b = valid_base.clone();
    b.doc_link = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 7. missing protocol
    let mut b = valid_base.clone();
    b.protocol = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 8. missing framing
    let mut b = valid_base.clone();
    b.framing = String::new();
    assert!(build_spec_from_config(&app_config, "config_server", b).is_err());

    // 9. unknown capability with no addresses
    assert!(build_spec_from_config(&app_config, "unknown_capability", valid_base).is_err());
}

//-----------------------------------------------------------------------------------------------
#[tokio::test]
async fn test_publish_service_spec_fail_fast() {
    let valid_base = ServiceSpec {
        name: "Config Server".to_string(),
        tag: "config-server-mfe".to_string(),
        layer: "L1".to_string(),
        category: "Base Fleet".to_string(),
        description: "Centralized configuration repository.".to_string(),
        doc_link: "obsidian-brain/06-Microservices/Config-Server-Hub.md".to_string(),
        protocol: "TCP".to_string(),
        framing: "Port %s TCP".to_string(),
        ..Default::default()
    };

    // 1. web_interface missing
    let app_config = AppConfig::default();
    let res = publish_service_spec(&app_config, None, "config_server", valid_base.clone());
    assert!(res.is_err(), "publish_service_spec must FAIL FAST when web_interface is missing");

    let sync_res = publish_service_spec_sync(&app_config, None, "config_server", valid_base).await;
    assert!(sync_res.is_err(), "publish_service_spec_sync must FAIL FAST when web_interface is missing");
}

//-----------------------------------------------------------------------------------------------
#[test]
fn test_exchange_contract_serialization() {
    let spec = ServiceSpec {
        name: "log_server".to_string(),
        tag: "log-server-inspector".to_string(),
        contracts: vec![ExchangeContract {
            id: "protobuf".to_string(),
            r#type: "gRPC / Protobuf".to_string(),
            tab_label: "Protobuf API Spec".to_string(),
            port: 9021,
            peers: vec![ContractPeer {
                service: "web_interface".to_string(),
                role: "consumer".to_string(),
                description: "Log bridge SSE proxy".to_string(),
            }],
            operations: vec![ContractOperation {
                name: "GetTailLogs".to_string(),
                kind: "RPC".to_string(),
                target: "logservice.LogBridge/GetTailLogs".to_string(),
                input: "TailLogsRequest".to_string(),
                output: "TailLogsResponse".to_string(),
                description: "Fetch ring buffer tail".to_string(),
            }],
            schema_format: "proto3".to_string(),
            schema: "syntax = \"proto3\";".to_string(),
            ..Default::default()
        }],
        ..Default::default()
    };

    let json = serde_json::to_string(&spec).expect("serialize ServiceSpec contracts");
    assert!(json.contains("\"tabLabel\":\"Protobuf API Spec\""));
    assert!(json.contains("\"schemaFormat\":\"proto3\""));
}
