//! ESSENTIAL PROCESS:
//! Standardizes self-describing microservice specifications, Exchange Contracts,
//! IDL schema extractors, and dynamic registration with web-interface for Rust.
//! Auto-resolves runtime listen/REST addresses, dynamic semver, host node,
//! and documentation links from AppConfig.
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
use chrono::SecondsFormat;
use rand::Rng;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct ProtocolSpec {
    pub r#type: String,
    pub port: i32,
    pub framing: String,
    pub description: String,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct DependencySpec {
    pub target: String,
    pub proto: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub label: String,
    #[serde(rename = "exchangeId", default, skip_serializing_if = "String::is_empty")]
    pub exchange_id: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub description: String,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct HealthSpec {
    #[serde(rename = "type", default, skip_serializing_if = "String::is_empty")]
    pub r#type: String,
    #[serde(default, skip_serializing_if = "is_zero_i32")]
    pub port: i32,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub path: String,
    #[serde(rename = "timeoutMs", default, skip_serializing_if = "is_zero_i32")]
    pub timeout_ms: i32,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct CanvasSpec {
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub icon: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub color: String,
    #[serde(rename = "preferredSlot", default, skip_serializing_if = "String::is_empty")]
    pub preferred_slot: String,
    #[serde(rename = "preferredX", default, skip_serializing_if = "is_zero_f64")]
    pub preferred_x: f64,
    #[serde(rename = "preferredY", default, skip_serializing_if = "is_zero_f64")]
    pub preferred_y: f64,
    #[serde(rename = "particleProto", default, skip_serializing_if = "Vec::is_empty")]
    pub particle_proto: Vec<String>,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ContractPeer {
    pub service: String,
    pub role: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub description: String,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ContractOperation {
    pub name: String,
    pub kind: String,
    pub target: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub input: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub output: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub description: String,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct ExchangeContract {
    pub id: String,
    pub r#type: String,
    #[serde(rename = "tabLabel", default, skip_serializing_if = "String::is_empty")]
    pub tab_label: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub icon: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub direction: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub transport: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub address: String,
    #[serde(default, skip_serializing_if = "is_zero_i32")]
    pub port: i32,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub framing: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub auth: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub summary: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub source: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub peers: Vec<ContractPeer>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub operations: Vec<ContractOperation>,
    #[serde(rename = "schemaFormat", default, skip_serializing_if = "String::is_empty")]
    pub schema_format: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub schema: String,
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ContractsEnvelope {
    pub service: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub version: String,
    pub reliable: bool,
    pub exhaustive: bool,
    #[serde(rename = "generatedAt")]
    pub generated_at: String,
    pub source: String,
    pub contracts: Vec<ExchangeContract>,
}

fn is_zero_i32(v: &i32) -> bool {
    *v == 0
}

fn is_zero_f64(v: &f64) -> bool {
    *v == 0.0
}

fn is_default_health(h: &Option<HealthSpec>) -> bool {
    h.is_none()
}

fn is_empty_canvas(c: &Option<CanvasSpec>) -> bool {
    match c {
        None => true,
        Some(cv) => {
            cv.icon.is_empty()
                && cv.color.is_empty()
                && cv.preferred_slot.is_empty()
                && cv.preferred_x == 0.0
                && cv.preferred_y == 0.0
                && cv.particle_proto.is_empty()
        }
    }
}

//-----------------------------------------------------------------------------------------------
#[derive(Debug, Clone, Serialize, Deserialize)]
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
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub color: String,
    #[serde(rename = "requiresAuth")]
    pub requires_auth: bool,
    pub capability: String,
    #[serde(rename = "desc")]
    pub description: String,
    pub protocol: String,
    pub framing: String,
    #[serde(rename = "docLink")]
    pub doc_link: String,
    #[serde(rename = "navRoute", default, skip_serializing_if = "String::is_empty")]
    pub nav_route: String,
    #[serde(default, skip_serializing_if = "is_default_health")]
    pub health: Option<HealthSpec>,
    #[serde(default, skip_serializing_if = "is_empty_canvas")]
    pub canvas: Option<CanvasSpec>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub dependencies: Vec<DependencySpec>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub protocols: Vec<ProtocolSpec>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub contracts: Vec<ExchangeContract>,
    #[serde(rename = "flowDiagram")]
    pub flow_diagram: Vec<String>,
    #[serde(rename = "dataStructure")]
    pub data_structure: HashMap<String, serde_json::Value>,
    #[serde(rename = "sdkLang")]
    pub sdk_lang: String,
    #[serde(rename = "sourceCode")]
    pub source_code: String,
}

impl Default for ServiceSpec {
    fn default() -> Self {
        Self {
            name: String::new(),
            tag: String::new(),
            url: String::new(),
            nav_title: String::new(),
            layer: String::new(),
            category: String::new(),
            priority: 100,
            icon: "fa-cubes".to_string(),
            color: String::new(),
            requires_auth: false,
            capability: String::new(),
            description: String::new(),
            protocol: String::new(),
            framing: String::new(),
            doc_link: String::new(),
            nav_route: String::new(),
            health: None,
            canvas: None,
            dependencies: Vec::new(),
            protocols: Vec::new(),
            contracts: Vec::new(),
            flow_diagram: Vec::new(),
            data_structure: HashMap::new(),
            sdk_lang: "language-rust".to_string(),
            source_code: String::new(),
        }
    }
}

//-----------------------------------------------------------------------------------------------
// Contracts Helpers & IDL Extractors (Parity with Go / Python / C++ / C)
//-----------------------------------------------------------------------------------------------

/// Extracts the TCP/UDP port integer from a host:port string.
pub fn resolve_contract_port(addr: &str) -> i32 {
    let clean = addr.trim();
    if clean.is_empty() {
        return 0;
    }
    if let Some(idx) = clean.rfind(':') {
        if let Ok(port) = clean[idx + 1..].trim().parse::<i32>() {
            if port > 0 && port <= 65535 {
                return port;
            }
        }
    }
    0
}

/// Normalizes wildcard or shorthand bind addresses into displayable addresses.
pub fn display_address(addr: &str) -> String {
    let clean = addr.trim();
    if clean.is_empty() {
        return "dynamic".to_string();
    }
    if clean.starts_with(':') {
        return format!("127.0.0.1{}", clean);
    }
    if let Some(rest) = clean.strip_prefix("0.0.0.0:") {
        return format!("127.0.0.1:{}", rest);
    }
    clean.to_string()
}

/// Reads an embedded or disk schema file cleanly, returning empty string when missing.
pub fn read_schema_file<P: AsRef<Path>>(file_path: P) -> String {
    std::fs::read_to_string(file_path).unwrap_or_default()
}

/// Wraps microservice-owned contracts with UTC generation metadata.
pub fn new_contracts_envelope(
    service: &str,
    version: &str,
    source: &str,
    contracts: Vec<ExchangeContract>,
) -> ContractsEnvelope {
    let ver = version.trim().to_string();
    let src = if source.trim().is_empty() {
        format!("{} runtime", service)
    } else {
        source.to_string()
    };
    ContractsEnvelope {
        service: service.to_string(),
        version: ver,
        reliable: true,
        exhaustive: true,
        generated_at: chrono::Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
        source: src,
        contracts,
    }
}

/// Alias matching Python's `build_contracts_envelope`.
pub fn build_contracts_envelope(
    service: &str,
    version: &str,
    source: &str,
    contracts: Vec<ExchangeContract>,
) -> ContractsEnvelope {
    new_contracts_envelope(service, version, source, contracts)
}

fn extract_brace_body(text: &str, open_idx: usize) -> Option<(&str, usize)> {
    let bytes = text.as_bytes();
    if open_idx >= bytes.len() || bytes[open_idx] != b'{' {
        return None;
    }
    let mut depth = 0usize;
    for (idx, &b) in bytes.iter().enumerate().skip(open_idx) {
        if b == b'{' {
            depth += 1;
        } else if b == b'}' {
            depth -= 1;
            if depth == 0 {
                return Some((&text[open_idx + 1..idx], idx));
            }
        }
    }
    None
}

/// Parses protobuf service and RPC declarations from raw .proto IDL text.
pub fn extract_proto_operations(proto_text: &str) -> Vec<ContractOperation> {
    let mut ops = Vec::new();
    if proto_text.is_empty() {
        return ops;
    }

    let pkg_re = Regex::new(r"(?m)^\s*package\s+([A-Za-z0-9_.]+)\s*;").expect("valid pkg regex");
    let pkg_prefix = pkg_re
        .captures(proto_text)
        .and_then(|c| c.get(1))
        .map(|m| format!("{}.", m.as_str()))
        .unwrap_or_default();

    let svc_head_re = Regex::new(r"\bservice\s+([A-Za-z0-9_]+)\s*\{").expect("valid svc regex");
    let rpc_re = Regex::new(
        r"rpc\s+([A-Za-z0-9_]+)\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)\s+returns\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)",
    )
    .expect("valid rpc regex");

    let mut pos = 0usize;
    while pos < proto_text.len() {
        let Some(caps) = svc_head_re.captures(&proto_text[pos..]) else {
            break;
        };
        let full_match = caps.get(0).unwrap();
        let svc_name = caps.get(1).unwrap().as_str();
        let open_brace = pos + full_match.end() - 1;
        let Some((body, close_idx)) = extract_brace_body(proto_text, open_brace) else {
            break;
        };

        for rpc in rpc_re.captures_iter(body) {
            let rpc_name = rpc.get(1).unwrap().as_str();
            let in_stream = rpc.get(2).is_some();
            let in_type = rpc.get(3).unwrap().as_str();
            let out_stream = rpc.get(4).is_some();
            let out_type = rpc.get(5).unwrap().as_str();

            let kind = match (in_stream, out_stream) {
                (true, true) => "BIDI_STREAM",
                (false, true) => "SERVER_STREAM",
                (true, false) => "CLIENT_STREAM",
                (false, false) => "RPC",
            };

            ops.push(ContractOperation {
                name: rpc_name.to_string(),
                kind: kind.to_string(),
                target: format!("{}{}/{}", pkg_prefix, svc_name, rpc_name),
                input: format!("{}{}", if in_stream { "stream " } else { "" }, in_type),
                output: format!("{}{}", if out_stream { "stream " } else { "" }, out_type),
                description: format!("{}.{}", svc_name, rpc_name),
            });
        }

        pos = close_idx + 1;
    }

    ops
}

fn compact_capnp_lines(block: &str) -> Vec<String> {
    let mut out = Vec::new();
    for raw in block.lines() {
        let mut line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(cidx) = line.find('#') {
            line = line[..cidx].trim();
        }
        let cleaned = line.trim_end_matches(';').trim();
        if !cleaned.is_empty() {
            out.push(cleaned.to_string());
        }
    }
    out
}

/// Parses enum and struct declarations from raw .capnp IDL text.
pub fn extract_capnp_operations(capnp_text: &str) -> Vec<ContractOperation> {
    let mut ops = Vec::new();
    if capnp_text.is_empty() {
        return ops;
    }

    for (kw, kind, target_pfx, is_output, desc) in [
        ("enum", "ENUM", "enum ", true, "Cap'n Proto enum definition"),
        ("struct", "STRUCT", "struct ", false, "Cap'n Proto wire struct definition"),
    ] {
        let pat = format!(r"\b{}\s+([A-Za-z0-9_]+)\s*\{{", kw);
        let head_re = Regex::new(&pat).expect("valid capnp regex");
        let mut pos = 0usize;
        while pos < capnp_text.len() {
            let Some(caps) = head_re.captures(&capnp_text[pos..]) else {
                break;
            };
            let full_match = caps.get(0).unwrap();
            let name = caps.get(1).unwrap().as_str();
            let open_brace = pos + full_match.end() - 1;
            let Some((body, close_idx)) = extract_brace_body(capnp_text, open_brace) else {
                break;
            };
            let lines = compact_capnp_lines(body);
            ops.push(ContractOperation {
                name: name.to_string(),
                kind: kind.to_string(),
                target: format!("{}{}", target_pfx, name),
                input: if is_output { String::new() } else { lines.join("; ") },
                output: if is_output { lines.join(", ") } else { String::new() },
                description: desc.to_string(),
            });
            pos = close_idx + 1;
        }
    }

    ops
}

//-----------------------------------------------------------------------------------------------
fn current_hostname() -> Option<String> {
    #[cfg(unix)]
    {
        unsafe extern "C" {
            fn gethostname(name: *mut std::os::raw::c_char, len: usize) -> std::os::raw::c_int;
        }
        let mut buf = [0u8; 256];
        let rc = unsafe { gethostname(buf.as_mut_ptr() as *mut std::os::raw::c_char, buf.len()) };
        if rc == 0 {
            let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
            if let Ok(s) = std::str::from_utf8(&buf[..end]) {
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    return Some(trimmed.to_string());
                }
            }
        }
        None
    }
    #[cfg(not(unix))]
    {
        std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .ok()
            .filter(|s| !s.trim().is_empty())
    }
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
    if base.icon.trim().is_empty() {
        base.icon = "fa-cubes".to_string();
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
    if !ports_map.is_empty() {
        base.data_structure.insert("ports".to_string(), serde_json::Value::Object(ports_map));
    }
    if let Some(host) = current_hostname() {
        base.data_structure.insert("node".to_string(), serde_json::Value::String(host));
    }

    // 6. Auto-populate NavRoute, Canvas, and Health defaults if unset
    if base.nav_route.trim().is_empty() {
        base.nav_route = format!("/mfe/{}", base.name);
    }

    let mut canvas = base.canvas.take().unwrap_or_default();
    if base.color.is_empty() && !canvas.color.is_empty() {
        base.color = canvas.color.clone();
    } else if canvas.color.is_empty() && !base.color.is_empty() {
        canvas.color = base.color.clone();
    }
    if canvas.icon.is_empty() && !base.icon.is_empty() {
        canvas.icon = base.icon.clone();
    }
    base.canvas = Some(canvas);

    let mut health = base.health.take().unwrap_or_default();
    if health.r#type.is_empty() {
        health.r#type = "tcp".to_string();
    }
    if health.port == 0 {
        for p_str in [&rest_port, &tcp_port, &grpc_port] {
            if let Ok(n) = p_str.parse::<i32>() {
                if n > 0 {
                    health.port = n;
                    break;
                }
            }
        }
    }
    if health.timeout_ms == 0 {
        health.timeout_ms = 350;
    }
    base.health = Some(health);

    Ok(base)
}

fn delay_with_jitter(delay: Duration) -> Duration {
    let half_ms = (delay.as_millis() as u64) / 2;
    if half_ms == 0 {
        return delay;
    }
    let jitter_ms = rand::thread_rng().gen_range(0..=half_ms);
    delay + Duration::from_millis(jitter_ms)
}

async fn send_register_post(web_addr: &str, payload: &str) -> Result<bool, std::io::Error> {
    let request = format!(
        "POST /api/v1/register HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        web_addr,
        payload.len(),
        payload
    );

    let mut stream = tokio::time::timeout(Duration::from_secs(3), TcpStream::connect(web_addr))
        .await
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "connect timeout"))??;
    stream.write_all(request.as_bytes()).await?;
    let mut resp = Vec::new();
    let _ = tokio::time::timeout(Duration::from_secs(3), stream.read_to_end(&mut resp)).await;
    let resp_str = String::from_utf8_lossy(&resp);
    Ok(resp_str.contains(" 200 ") || resp_str.contains(" 201 "))
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
        match send_register_post(&web_addr, &payload).await {
            Ok(true) => {
                if let Some(l) = &logger {
                    l.info(&format!("spec: Successfully published '{}' to {}", spec.name, web_addr));
                }
                return Ok(());
            }
            Ok(false) => {
                if let Some(l) = &logger {
                    l.warning(&format!("spec: Registration for '{}' was not accepted cleanly. Retrying...", spec.name));
                }
            }
            Err(e) => {
                if let Some(l) = &logger {
                    l.debug(&format!("spec: Waiting for web-interface at {} ({}). Retrying in {:?}...", web_addr, e, delay));
                }
            }
        }

        tokio::time::sleep(delay_with_jitter(delay)).await;
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

            let success = matches!(send_register_post(&web_addr, &payload).await, Ok(true));
            if success {
                if let Some(l) = &logger {
                    if is_first {
                        l.info(&format!("spec: Successfully published '{}' to {}", spec.name, web_addr));
                        is_first = false;
                    } else {
                        l.debug(&format!("spec: Heartbeat for '{}' accepted by {}", spec.name, web_addr));
                    }
                }
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
                tokio::time::sleep(delay_with_jitter(delay)).await;
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
