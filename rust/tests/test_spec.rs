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

//-----------------------------------------------------------------------------------------------
#[test]
fn test_contracts_envelope_and_extractors_parity() {
    use microservice_toolbox::contracts::*;

    let proto = r#"
syntax = "proto3";
package demo.v1;
service DemoControl {
  option (google.api.default_host) = { host: "localhost" };
  rpc Ping (PingReq) returns (PingResp);
  rpc StreamEvents (stream EventReq) returns (stream EventResp);
}
"#;
    let ops = extract_proto_operations(proto);
    assert_eq!(ops.len(), 2);
    assert_eq!(ops[0].kind, "RPC");
    assert_eq!(ops[0].target, "demo.v1.DemoControl/Ping");
    assert_eq!(ops[1].kind, "BIDI_STREAM");

    let capnp = r#"
enum Level {
  info @0; # info level
  error @1;
}
struct Packet {
  id @0 :Text;
  payload @1 :Data;
}
"#;
    let cap_ops = extract_capnp_operations(capnp);
    assert_eq!(cap_ops.len(), 2);
    assert_eq!(cap_ops[0].kind, "ENUM");
    assert_eq!(cap_ops[1].kind, "STRUCT");

    assert_eq!(resolve_contract_port("0.0.0.0:9021"), 9021);
    assert_eq!(display_address(":3308"), "127.0.0.1:3308");
    assert_eq!(display_address(""), "dynamic");

    let env = new_contracts_envelope(
        "rust_svc",
        "1.0.0",
        "unit test",
        vec![ExchangeContract {
            id: "grpc".to_string(),
            r#type: "gRPC".to_string(),
            operations: ops,
            ..Default::default()
        }],
    );
    assert!(env.reliable && env.exhaustive);
    assert_eq!(env.contracts.len(), 1);
}

#[test]
fn test_spec_enhanced_metadata_and_node() {
    use microservice_toolbox::spec::{CanvasSpec, DependencySpec};

    let yaml_str = r#"
capabilities:
  pay_gw:
    ip: "127.0.0.1"
    rest_port: "8099"
"#;
    let data: serde_yml::Value = serde_yml::from_str(yaml_str).unwrap();
    let app_config = AppConfig::from_value(data);
    let base = ServiceSpec {
        name: "Payment Gateway".to_string(),
        tag: "payment-gateway-mfe".to_string(),
        layer: "L2".to_string(),
        category: "Domain Services".to_string(),
        color: "#38bdf8".to_string(),
        description: "Handles payments.".to_string(),
        doc_link: "doc.md".to_string(),
        protocol: "REST".to_string(),
        framing: "Port %s REST".to_string(),
        dependencies: vec![DependencySpec {
            target: "notif_server".to_string(),
            proto: "grpc".to_string(),
            label: "Alerts".to_string(),
            ..Default::default()
        }],
        canvas: Some(CanvasSpec {
            preferred_slot: "domain".to_string(),
            ..Default::default()
        }),
        ..Default::default()
    };

    let spec = build_spec_from_config(&app_config, "pay_gw", base).unwrap();
    assert_eq!(spec.nav_route, "/mfe/Payment Gateway");
    assert_eq!(spec.canvas.as_ref().unwrap().color, "#38bdf8");
    assert_eq!(spec.health.as_ref().unwrap().port, 8099);
    assert!(spec.data_structure.get("node").is_some());
}

#[test]
fn test_spec_brain_id_explicit_and_omitted() {
    let yaml_str = r#"
capabilities:
  pay_gw:
    ip: "127.0.0.1"
    rest_port: "8099"
"#;
    let data: serde_yml::Value = serde_yml::from_str(yaml_str).unwrap();
    let app_config = AppConfig::from_value(data);
    let base = ServiceSpec {
        name: "Payment Gateway".to_string(),
        tag: "payment-gateway-mfe".to_string(),
        layer: "L2".to_string(),
        category: "Domain Services".to_string(),
        description: "Handles payments.".to_string(),
        doc_link: "doc.md".to_string(),
        protocol: "REST".to_string(),
        framing: "Port %s REST".to_string(),
        brain_id: Some("brain-rust".to_string()),
        ..Default::default()
    };

    let spec = build_spec_from_config(&app_config, "pay_gw", base).unwrap();
    assert_eq!(spec.brain_id.as_deref(), Some("brain-rust"));
    let json = serde_json::to_string(&spec).unwrap();
    assert!(json.contains("\"brain_id\":\"brain-rust\""));

    let mut base_none = spec.clone();
    base_none.brain_id = None;
    let json_none = serde_json::to_string(&base_none).unwrap();
    assert!(!json_none.contains("\"brain_id\""));
}

//-----------------------------------------------------------------------------------------------
#[test]
fn test_spec_brain_id_priority_and_standalone_yaml_zero_env() {
    use std::sync::Mutex;

    static ENV_LOCK: Mutex<()> = Mutex::new(());
    let _guard = ENV_LOCK.lock().unwrap();

    let base = ServiceSpec {
        name: "Order Router".to_string(),
        tag: "order-router-mfe".to_string(),
        layer: "L3".to_string(),
        category: "Domain Services".to_string(),
        description: "Routes trading orders.".to_string(),
        doc_link: "obsidian-brain/06-Microservices/Order-Router.md".to_string(),
        protocol: "TCP".to_string(),
        framing: "Port %s TCP".to_string(),
        ..Default::default()
    };

    let make_cfg = |yaml: &str| -> AppConfig {
        let data: serde_yml::Value = serde_yml::from_str(yaml).unwrap();
        AppConfig::from_value(data)
    };

    unsafe {
        std::env::remove_var("BRAIN_ID");
        std::env::set_var("TARGET_BRAIN_ID", "env-target");
    }

    // 1. TARGET_BRAIN_ID fallback when capabilities and BRAIN_ID are absent
    let cfg_env = make_cfg(
        r#"
capabilities:
  order_router:
    ip: "127.0.0.1"
    port: "14100"
"#,
    );
    let spec_target = build_spec_from_config(&cfg_env, "order_router", base.clone()).unwrap();
    assert_eq!(spec_target.brain_id.as_deref(), Some("env-target"));

    // 2. BRAIN_ID > TARGET_BRAIN_ID
    unsafe {
        std::env::set_var("BRAIN_ID", "env-primary");
    }
    let spec_primary = build_spec_from_config(&cfg_env, "order_router", base.clone()).unwrap();
    assert_eq!(spec_primary.brain_id.as_deref(), Some("env-primary"));

    // 3. watchdog_agent.brain_id > BRAIN_ID
    let cfg_wd = make_cfg(
        r#"
capabilities:
  order_router:
    ip: "127.0.0.1"
    port: "14100"
  watchdog_agent:
    brain_id: "watchdog-brain"
"#,
    );
    let spec_wd = build_spec_from_config(&cfg_wd, "order_router", base.clone()).unwrap();
    assert_eq!(spec_wd.brain_id.as_deref(), Some("watchdog-brain"));

    // 4. squad_agent.target_brain_id > watchdog_agent.brain_id
    let cfg_sq = make_cfg(
        r#"
capabilities:
  order_router:
    ip: "127.0.0.1"
    port: "14100"
  watchdog_agent:
    brain_id: "watchdog-brain"
  squad_agent:
    target_brain_id: "squad-brain"
"#,
    );
    let spec_sq = build_spec_from_config(&cfg_sq, "order_router", base.clone()).unwrap();
    assert_eq!(spec_sq.brain_id.as_deref(), Some("squad-brain"));

    // 5. Loading standalone.yaml with target_brain_id: "trading-brain" and ZERO env vars set
    let tmp_dir = std::env::temp_dir().join("rust_toolbox_spec_brain_id_test");
    let _ = std::fs::create_dir_all(&tmp_dir);
    let yaml_path = tmp_dir.join("standalone.yaml");
    let yaml_content = r#"
common:
  name: order_router
capabilities:
  order_router:
    ip: "127.0.0.1"
    port: "14100"
  squad_agent:
    target_brain_id: "trading-brain"
"#;
    std::fs::write(&yaml_path, yaml_content).unwrap();

    unsafe {
        std::env::remove_var("BRAIN_ID");
        std::env::remove_var("TARGET_BRAIN_ID");
        std::env::remove_var("SHARED_CONFIG_PATH");
        std::env::set_var("CONFIG_PATH", &yaml_path);
    }
    let loaded_cfg = AppConfig::load_config("standalone_brain_test", None).unwrap();
    unsafe {
        std::env::remove_var("CONFIG_PATH");
    }
    let _ = std::fs::remove_file(&yaml_path);
    let _ = std::fs::remove_dir(&tmp_dir);

    let spec_loaded = build_spec_from_config(&loaded_cfg, "order_router", base).unwrap();
    assert_eq!(spec_loaded.brain_id.as_deref(), Some("trading-brain"));
}
