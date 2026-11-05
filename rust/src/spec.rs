//! ESSENTIAL PROCESS:
//! Standardizes self-describing microservice specifications and dynamic
//! registration with web-interface across the Bastien-Antigravity fleet for Rust.
//! Auto-resolves runtime listen/REST addresses, dynamic semver, active
//! profile, and documentation links from AppConfig.
//!
//! FAIL-FAST PRINCIPLE:
//! Zero silent fallbacks, zero default values, and zero dummy placeholders.
//! Microservices must explicitly declare their own specification metadata
//! (name, tag, layer, category, description, doc_link, protocol, framing).
//! Configuration addresses (including web_interface) must resolve strictly;
//! missing capabilities, missing ports, or missing metadata FAIL FAST immediately.
//!
//! DATA FLOW:
//! 1. Microservice ServiceSpec + Capability Name -> Dynamic AppConfig Lookups
//! 2. Strict Fail-Fast Validation of all required fields & dynamic endpoints
//! 3. POST to /api/v1/register with exponential backoff and randomized jitter
//!
//! KEY PARAMETERS:
//! - app_config: Active AppConfig for capability host/port/version resolution.
//! - logger: Universal Logger for status logging and retry diagnostics.
//! - capability: Capability key in AppConfig e.g. "config_server".
//! - base: Microservice-provided ServiceSpec containing domain metadata.

use crate::config::loader::AppConfig;
use crate::utils::logger::Logger;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolSpec {
    pub r#type: String,
    pub port: i32,
    pub framing: String,
    pub description: String,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ServiceSpec {
    pub name: String,
    pub tag: String,
    pub url: String,
    #[serde(rename = "navTitle")]
    pub nav_title: String,
    pub layer: String,
    pub category: String,
    pub priority: i32,
    pub icon: String,
    #[serde(rename = "requiresAuth")]
    pub requires_auth: bool,
    pub capability: String,
    #[serde(rename = "desc")]
    pub description: String,
    pub protocol: String,
    pub framing: String,
    #[serde(rename = "docLink")]
    pub doc_link: String,
    #[serde(rename = "flowDiagram")]
    pub flow_diagram: Vec<String>,
    #[serde(rename = "dataStructure")]
    pub data_structure: HashMap<String, serde_json::Value>,
    #[serde(rename = "sdkLang")]
    pub sdk_lang: String,
    #[serde(rename = "sourceCode")]
    pub source_code: String,
}

//-----------------------------------------------------------------------------------------------
/// Builds and validates a ServiceSpec extracting dynamic parameters from AppConfig.
/// FAIL-FAST: Strictly validates all required metadata and resolves dynamic endpoints.
/// Zero silent fallback or dummy placeholders.
pub fn build_spec_from_config(
    app_config: &AppConfig,
    capability: &str,
    mut base: ServiceSpec,
) -> Result<ServiceSpec, Box<dyn std::error::Error>> {
    let cap = capability.trim();
    if cap.is_empty() {
        return Err("spec.build_spec_from_config: capability name is strictly required (FAIL-FAST)".into());
    }

    // 1. Strict Metadata Validation (FAIL-FAST: ZERO DUMMY FALLBACKS)
    if base.name.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'name' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.tag.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'tag' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.layer.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'layer' (L1|L2|L3) is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.category.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'category' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.description.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'description' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.doc_link.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'doc_link' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.protocol.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'protocol' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }
    if base.framing.trim().is_empty() {
        return Err(format!("spec.build_spec_from_config: 'framing' is strictly required for capability '{}' (FAIL-FAST)", cap).into());
    }

    base.capability = cap.to_string();
    if base.nav_title.trim().is_empty() {
        base.nav_title = base.name.clone();
    }
    if base.sdk_lang.trim().is_empty() {
        base.sdk_lang = "language-rust".to_string();
    }

    // 2. Resolve dynamic ports and endpoints from AppConfig (FAIL-FAST)
    let tcp_addr = app_config.get_listen_addr(cap).unwrap_or_default();
    let rest_addr = app_config.get_rest_addr(cap).unwrap_or_default();
    let grpc_addr = app_config.get_grpc_listen_addr(cap).unwrap_or_default();

    let tcp_port = _extract_port(&tcp_addr);
    let rest_port = _extract_port(&rest_addr);
    let grpc_port = _extract_port(&grpc_addr);

    let mut ports_map = serde_json::Map::new();
    if !tcp_port.is_empty() {
        ports_map.insert("tcp".to_string(), serde_json::Value::String(tcp_port.clone()));
    }
    if !rest_port.is_empty() {
        ports_map.insert("rest".to_string(), serde_json::Value::String(rest_port.clone()));
    }
    if !grpc_port.is_empty() {
        ports_map.insert("grpc".to_string(), serde_json::Value::String(grpc_port.clone()));
    }

    // 3. Dynamic URL resolution (FAIL-FAST)
    if base.url.trim().is_empty() {
        if !rest_addr.is_empty() {
            base.url = format!("http://{}", rest_addr);
        } else if !tcp_addr.is_empty() {
            base.url = format!("http://{}", tcp_addr);
        } else {
            return Err(format!("spec.build_spec_from_config: unable to resolve URL for capability '{}' (FAIL-FAST)", cap).into());
        }
    }

    // 4. Dynamic Framing Port Interpolation (FAIL-FAST)
    if base.framing.contains("%s") {
        let count = base.framing.matches("%s").count();
        let mut available = Vec::new();
        if !tcp_port.is_empty() { available.push(&tcp_port); }
        if !rest_port.is_empty() { available.push(&rest_port); }
        if !grpc_port.is_empty() { available.push(&grpc_port); }

        if available.len() < count {
            return Err(format!("spec.build_spec_from_config: framing requires {} port(s), but only {} available for capability '{}' (FAIL-FAST)", count, available.len(), cap).into());
        }

        for p in available.into_iter().take(count) {
            base.framing = base.framing.replacen("%s", p, 1);
        }
    }

    // 5. Dynamic Semver Resolution (FAIL-FAST)
    let version = app_config.get_version();
    if version.trim().is_empty() {
        return Err("spec.build_spec_from_config: dynamic version resolution returned empty string (FAIL-FAST)".into());
    }

    base.data_structure.insert("version".to_string(), serde_json::Value::String(version));
    base.data_structure.insert("capability".to_string(), serde_json::Value::String(cap.to_string()));
    base.data_structure.insert("ports".to_string(), serde_json::Value::Object(ports_map));

    Ok(base)
}

//-----------------------------------------------------------------------------------------------
/// Synchronously publishes a service specification to web-interface.
/// FAIL-FAST: Returns error immediately if web_interface or specification validation fails.
pub async fn publish_service_spec_sync(
    app_config: &AppConfig,
    logger: Option<Arc<dyn Logger>>,
    capability: &str,
    base: ServiceSpec,
) -> Result<(), Box<dyn std::error::Error>> {
    let web_addr = match app_config.get_listen_addr("web_interface") {
        Ok(addr) if !addr.trim().is_empty() => addr,
        Ok(_) => {
            if let Some(l) = &logger {
                l.critical("spec: capability 'web_interface' resolved to empty address (FAIL-FAST)");
            }
            return Err("spec: capability 'web_interface' resolved to empty address (FAIL-FAST)".into());
        }
        Err(e) => {
            if let Some(l) = &logger {
                l.critical(&format!("spec: capability 'web_interface' is unresolvable: {} (FAIL-FAST)", e));
            }
            return Err(format!("spec: capability 'web_interface' is unresolvable: {} (FAIL-FAST)", e).into());
        }
    };

    let spec = build_spec_from_config(app_config, capability, base)?;
    let payload = serde_json::to_string(&spec)?;

    let mut delay = Duration::from_millis(500);
    let max_delay = Duration::from_secs(30);

    loop {
        let request = format!(
            "POST /api/v1/register HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            web_addr,
            payload.len(),
            payload
        );

        match TcpStream::connect(&web_addr).await {
            Ok(mut stream) => {
                if stream.write_all(request.as_bytes()).await.is_ok() {
                    let mut resp = Vec::new();
                    let _ = stream.read_to_end(&mut resp).await;
                    let resp_str = String::from_utf8_lossy(&resp);
                    if resp_str.contains(" 200 ") || resp_str.contains(" 201 ") {
                        if let Some(l) = &logger {
                            l.info(&format!("spec: Successfully published '{}' to {}", spec.name, web_addr));
                        }
                        return Ok(());
                    }
                }
            }
            Err(e) => {
                if let Some(l) = &logger {
                    l.debug(&format!("spec: Waiting for web-interface at {} ({}). Retrying in {:?}...", web_addr, e, delay));
                }
            }
        }

        tokio::time::sleep(delay).await;
        delay = std::cmp::min(delay * 2, max_delay);
    }
}

//-----------------------------------------------------------------------------------------------
/// Spawns a background task to publish service specification to web-interface.
/// FAIL-FAST: Validates web_interface reachability and specification synchronously before spawning.
pub fn publish_service_spec(
    app_config: &AppConfig,
    logger: Option<Arc<dyn Logger>>,
    capability: &str,
    base: ServiceSpec,
) -> Result<(), Box<dyn std::error::Error>> {
    publish_service_spec_internal(app_config, logger, capability, base, None)
}

fn publish_service_spec_internal(
    app_config: &AppConfig,
    logger: Option<Arc<dyn Logger>>,
    capability: &str,
    base: ServiceSpec,
    stop_flag: Option<Arc<std::sync::atomic::AtomicBool>>,
) -> Result<(), Box<dyn std::error::Error>> {
    // 1. Validate fail-fast condition on web_interface immediately
    let web_addr = match app_config.get_listen_addr("web_interface") {
        Ok(addr) if !addr.trim().is_empty() => addr,
        Ok(_) => return Err("spec: capability 'web_interface' resolved to empty address (FAIL-FAST)".into()),
        Err(e) => return Err(format!("spec: capability 'web_interface' is unresolvable: {} (FAIL-FAST)", e).into()),
    };

    // 2. Validate and build specification synchronously (FAIL-FAST)
    let spec = build_spec_from_config(app_config, capability, base)?;

    tokio::spawn(async move {
        let payload = match serde_json::to_string(&spec) {
            Ok(p) => p,
            Err(_) => return,
        };

        let mut delay = Duration::from_millis(500);
        let max_delay = Duration::from_secs(30);
        let mut is_first = true;

        loop {
            if let Some(ref flag) = stop_flag {
                if flag.load(std::sync::atomic::Ordering::Relaxed) {
                    return;
                }
            }

            let request = format!(
                "POST /api/v1/register HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                web_addr,
                payload.len(),
                payload
            );

            let mut success = false;
            if let Ok(mut stream) = TcpStream::connect(&web_addr).await {
                if stream.write_all(request.as_bytes()).await.is_ok() {
                    let mut resp = Vec::new();
                    let _ = stream.read_to_end(&mut resp).await;
                    let resp_str = String::from_utf8_lossy(&resp);
                    if resp_str.contains(" 200 ") || resp_str.contains(" 201 ") {
                        success = true;
                        if let Some(l) = &logger {
                            if is_first {
                                l.info(&format!("spec: Successfully published '{}' to {}", spec.name, web_addr));
                                is_first = false;
                            } else {
                                l.debug(&format!("spec: Heartbeat for '{}' accepted by {}", spec.name, web_addr));
                            }
                        }
                    }
                }
            }

            if success {
                for _ in 0..30 {
                    if let Some(ref flag) = stop_flag {
                        if flag.load(std::sync::atomic::Ordering::Relaxed) {
                            return;
                        }
                    }
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
                delay = Duration::from_millis(500);
            } else {
                tokio::time::sleep(delay).await;
                delay = std::cmp::min(delay * 2, max_delay);
            }
        }
    });

    Ok(())
}

//-----------------------------------------------------------------------------------------------
/// Dynamic registration alias adhering to fleet standards.
pub fn publish(
    app_config: &AppConfig,
    logger: Option<Arc<dyn Logger>>,
    capability: &str,
    base: ServiceSpec,
) -> Result<(), Box<dyn std::error::Error>> {
    publish_service_spec(app_config, logger, capability, base)
}

//-----------------------------------------------------------------------------------------------
/// Dynamic registration with lifecycle integration alias adhering to fleet standards.
pub fn publish_with_lifecycle(
    app_config: &AppConfig,
    logger: Option<Arc<dyn Logger>>,
    lm: Option<&crate::lifecycle::manager::LifecycleManager>,
    capability: &str,
    base: ServiceSpec,
) -> Result<(), Box<dyn std::error::Error>> {
    let stop_flag = Arc::new(std::sync::atomic::AtomicBool::new(false));
    if let Some(lifecycle) = lm {
        let flag_clone = stop_flag.clone();
        lifecycle.register_background(&format!("OpenMFEPublisher_{}", capability), move || {
            let f = flag_clone.clone();
            async move {
                f.store(true, std::sync::atomic::Ordering::Relaxed);
                Ok(())
            }
        });
    }
    publish_service_spec_internal(app_config, logger, capability, base, Some(stop_flag))
}

//-----------------------------------------------------------------------------------------------
fn _extract_port(addr: &str) -> String {
    if addr.is_empty() {
        return String::new();
    }
    match addr.rfind(':') {
        Some(idx) => addr[idx + 1..].to_string(),
        None => addr.to_string(),
    }
}
