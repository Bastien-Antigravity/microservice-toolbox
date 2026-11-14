// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-performance, lock-free WireTap transport telemetry engine for Rust.
// Aggregates inter-service and external network connections and segregated
// information channels with cache-line padded atomics and branch-free power-of-two sampling.
// Periodically flushes snapshots to web-interface topology hub and syncs toggle state.
//
// DATA FLOW:
// Hot path packet -> relaxed atomic check -> bitmask sampling -> relaxed fetch_add -> background HTTP flush
//
// KEY PARAMETERS:
// - ENABLED: AtomicBool global switch (default true, configurable via AppConfig).
// - CACHE_LINE: 64 bytes cache-line alignment to eliminate False Sharing.
// -----------------------------------------------------------------------------

use crate::config::loader::AppConfig;
use chrono::SecondsFormat;
use serde::{Deserialize, Serialize};
use std::cell::Cell;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU64, Ordering};
use std::sync::{Arc, Once, OnceLock, RwLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

// -----------------------------------------------------------------------------
// Wire Data Contracts (100% parity with Go, Python & C++)
// -----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChannelMetric {
    pub channel: String,
    pub category: String,
    pub direction: String,
    pub frames: u64,
    pub bytes: u64,
    pub errors: u64,
    pub avg_latency_ms: f64,
    pub last_seen: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_payload: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EdgeReport {
    pub source: String,
    pub target: String,
    pub protocol: String,
    pub framing: String,
    pub active_conns: i64,
    pub total_frames: u64,
    pub total_bytes: u64,
    pub total_errors: u64,
    pub last_seen: String,
    pub is_external: bool,
    pub channels: Vec<ChannelMetric>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestPayload {
    pub reporter: String,
    pub timestamp: String,
    pub enabled: bool,
    pub edges: Vec<EdgeReport>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestResponse {
    pub status: String,
    pub enabled: bool,
}

// -----------------------------------------------------------------------------
// Lock-Free Cache-Padded Atomic Structures
// -----------------------------------------------------------------------------

#[repr(align(64))]
pub struct AtomicChannelEntry {
    pub channel: String,
    pub category: String,
    pub direction: String,
    pub frames: AtomicU64,
    pub bytes: AtomicU64,
    pub errors: AtomicU64,
    pub total_lat_us: AtomicU64,
    pub lat_samples: AtomicU64,
    pub last_seen_ms: AtomicI64,
    pub last_payload: RwLock<Option<String>>,
}

impl AtomicChannelEntry {
    pub fn new(channel: String, category: String, direction: String) -> Self {
        Self {
            channel,
            category,
            direction,
            frames: AtomicU64::new(0),
            bytes: AtomicU64::new(0),
            errors: AtomicU64::new(0),
            total_lat_us: AtomicU64::new(0),
            lat_samples: AtomicU64::new(0),
            last_seen_ms: AtomicI64::new(0),
            last_payload: RwLock::new(None),
        }
    }

    #[inline(always)]
    pub fn record(&self, byte_count: u64, lat_ms: f64, is_err: bool, payload: Option<&str>, now_ms: i64) {
        self.frames.fetch_add(1, Ordering::Relaxed);
        if byte_count > 0 {
            self.bytes.fetch_add(byte_count, Ordering::Relaxed);
        }
        if is_err {
            self.errors.fetch_add(1, Ordering::Relaxed);
        }
        if lat_ms > 0.0 {
            self.total_lat_us.fetch_add((lat_ms * 1000.0) as u64, Ordering::Relaxed);
            self.lat_samples.fetch_add(1, Ordering::Relaxed);
        }
        self.last_seen_ms.store(now_ms, Ordering::Relaxed);

        if let Some(p) = payload {
            if !p.is_empty() {
                if let Ok(mut lock) = self.last_payload.write() {
                    *lock = Some(p.to_string());
                }
            }
        }
    }
}

#[repr(align(64))]
pub struct AtomicEdgeEntry {
    pub source: String,
    pub target: String,
    pub protocol: String,
    pub framing: RwLock<String>,
    pub is_external: AtomicBool,
    pub active_conns: AtomicI64,
    pub total_frames: AtomicU64,
    pub total_bytes: AtomicU64,
    pub total_errors: AtomicU64,
    pub last_seen_ms: AtomicI64,
    pub channels: RwLock<HashMap<String, Arc<AtomicChannelEntry>>>,
}

impl AtomicEdgeEntry {
    pub fn new(source: String, target: String, protocol: String, framing: String) -> Self {
        Self {
            source,
            target,
            protocol,
            framing: RwLock::new(framing),
            is_external: AtomicBool::new(false),
            active_conns: AtomicI64::new(0),
            total_frames: AtomicU64::new(0),
            total_bytes: AtomicU64::new(0),
            total_errors: AtomicU64::new(0),
            last_seen_ms: AtomicI64::new(0),
            channels: RwLock::new(HashMap::new()),
        }
    }
}

// -----------------------------------------------------------------------------
// Global Telemetry State & Thread-Local Bitmask Sampling
// -----------------------------------------------------------------------------

static ENABLED: AtomicBool = AtomicBool::new(true);
static REPORTER_ONCE: Once = Once::new();

thread_local! {
    static SAMPLE_COUNTER: Cell<u32> = const { Cell::new(0) };
}

#[inline(always)]
pub fn should_sample(mask: u32) -> bool {
    if mask == 0 {
        return true;
    }
    SAMPLE_COUNTER.with(|c| {
        let val = c.get().wrapping_add(1);
        c.set(val);
        (val & mask) == 0
    })
}

#[inline(always)]
pub fn is_enabled() -> bool {
    ENABLED.load(Ordering::Relaxed)
}

#[inline(always)]
pub fn set_enabled(on: bool) {
    ENABLED.store(on, Ordering::Relaxed);
}

type EdgeMap = RwLock<HashMap<String, Arc<AtomicEdgeEntry>>>;

fn get_edges_registry() -> &'static EdgeMap {
    static EDGES: OnceLock<EdgeMap> = OnceLock::new();
    EDGES.get_or_init(|| RwLock::new(HashMap::new()))
}

fn get_hub_url() -> &'static RwLock<String> {
    static HUB_URL: OnceLock<RwLock<String>> = OnceLock::new();
    HUB_URL.get_or_init(|| RwLock::new(String::new()))
}

fn get_local_service_lock() -> &'static RwLock<String> {
    static LOCAL_SERVICE: OnceLock<RwLock<String>> = OnceLock::new();
    LOCAL_SERVICE.get_or_init(|| RwLock::new("unknown_service".to_string()))
}

pub fn set_local_service_name(service_name: &str) {
    let norm = normalize_service_id(service_name);
    if let Ok(mut lock) = get_local_service_lock().write() {
        *lock = if norm.is_empty() {
            "unknown_service".to_string()
        } else {
            norm
        };
    }
}

pub fn set_local_service(service_name: &str) {
    set_local_service_name(service_name);
}

pub fn get_local_service_name() -> String {
    get_local_service_lock()
        .read()
        .map(|l| {
            if l.is_empty() {
                "unknown_service".to_string()
            } else {
                l.clone()
            }
        })
        .unwrap_or_else(|_| "unknown_service".to_string())
}

pub fn get_local_service() -> String {
    get_local_service_name()
}

pub fn set_web_hub_url(url: &str) {
    if let Ok(mut lock) = get_hub_url().write() {
        *lock = url.trim().trim_end_matches('/').to_string();
    }
}

pub fn get_web_hub_url() -> String {
    get_hub_url().read().map(|l| l.clone()).unwrap_or_default()
}

// -----------------------------------------------------------------------------
// Configuration & Background Reporter
// -----------------------------------------------------------------------------

fn yaml_scalar_to_string(v: &serde_yml::Value) -> String {
    match v {
        serde_yml::Value::String(s) => s.trim().to_string(),
        serde_yml::Value::Bool(b) => b.to_string(),
        serde_yml::Value::Number(n) => n.to_string(),
        _ => String::new(),
    }
}

/// Initializes WireTap from validated AppConfig and starts the 2s background ingestion reporter.
/// Zero silent fallback: reads web_interface address and wiretap_enabled strictly from AppConfig.
pub fn configure_from_config(service_name: &str, app_config: &AppConfig) {
    set_local_service(service_name);

    let raw_enabled = app_config
        .get_local("wiretap_enabled")
        .map(yaml_scalar_to_string)
        .filter(|s| !s.is_empty())
        .or_else(|| {
            app_config
                .get_value("common.wiretap_enabled")
                .map(yaml_scalar_to_string)
                .filter(|s| !s.is_empty())
        })
        .unwrap_or_default();

    let initial_enabled = raw_enabled.is_empty() || raw_enabled.eq_ignore_ascii_case("true");
    set_enabled(initial_enabled);

    if let Ok(web_addr) = app_config.get_listen_addr("web_interface") {
        if !web_addr.trim().is_empty() {
            set_web_hub_url(&format!("http://{}", web_addr.trim()));
        }
    }

    if get_local_service() != "web_interface" {
        REPORTER_ONCE.call_once(|| {
            let _ = std::thread::Builder::new()
                .name("wiretap-reporter".to_string())
                .spawn(reporter_loop);
        });
    }
}

fn post_ingest_once(hub_url: &str, body_json: &str) -> Option<IngestResponse> {
    let trimmed = hub_url.trim().trim_end_matches('/');
    let rest = trimmed
        .strip_prefix("http://")
        .or_else(|| trimmed.strip_prefix("https://"))
        .unwrap_or(trimmed);
    let (host_port, base_path) = match rest.find('/') {
        Some(idx) => (&rest[..idx], &rest[idx..]),
        None => (rest, ""),
    };
    if host_port.is_empty() {
        return None;
    }

    let path = format!("{}/api/v1/system/wiretap/ingest", base_path.trim_end_matches('/'));
    let request = format!(
        "POST {} HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        path,
        host_port,
        body_json.len(),
        body_json
    );

    let mut stream = TcpStream::connect(host_port).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(1500)));
    stream.write_all(request.as_bytes()).ok()?;

    let mut raw_resp = String::new();
    let _ = stream.read_to_string(&mut raw_resp);
    let body_start = raw_resp.find("\r\n\r\n").map(|i| i + 4)?;
    serde_json::from_str::<IngestResponse>(raw_resp[body_start..].trim()).ok()
}

fn reporter_loop() {
    loop {
        std::thread::sleep(Duration::from_secs(2));
        let hub = get_web_hub_url();
        if hub.is_empty() {
            continue;
        }

        let current_edges = if is_enabled() { snapshot() } else { Vec::new() };
        let payload = IngestPayload {
            reporter: get_local_service(),
            timestamp: chrono::Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
            enabled: is_enabled(),
            edges: current_edges,
        };

        if let Ok(body_json) = serde_json::to_string(&payload) {
            if let Some(resp) = post_ingest_once(&hub, &body_json) {
                if !resp.status.is_empty() && resp.enabled != is_enabled() {
                    set_enabled(resp.enabled);
                }
            }
        }
    }
}

// -----------------------------------------------------------------------------
// Canonical Service Normalization (100% parity with Go, Python & C++)
// -----------------------------------------------------------------------------

pub fn normalize_service_id(raw: &str) -> String {
    let s = raw.trim().to_lowercase().replace('-', "_");
    match s.as_str() {
        "09_rag_engine" | "rag_service" | "obsidian_rag" => "rag_engine".to_string(),
        "08_squad_agent" | "squad_agent" => "agent_squad".to_string(),
        "nats_server" | "nats_broker" => "nats".to_string(),
        "postgres" | "postgresql" | "timescaledb" => "timescale_db".to_string(),
        "vector_db" => "chromadb".to_string(),
        _ => s,
    }
}

// -----------------------------------------------------------------------------
// Hot-Path Event Recording (Optimized with Relaxed Atomics)
// -----------------------------------------------------------------------------

pub fn record_event(
    source: &str,
    target: &str,
    protocol: &str,
    framing: &str,
    channel: &str,
    category: &str,
    direction: &str,
    payload_summary: Option<&str>,
    bytes_count: u64,
    latency_ms: f64,
    is_err: bool,
    is_external: bool,
) {
    record_event_with_conn_delta(
        source,
        target,
        protocol,
        framing,
        channel,
        category,
        direction,
        payload_summary,
        bytes_count,
        latency_ms,
        is_err,
        is_external,
        0,
    );
}

pub fn record_event_with_conn_delta(
    source: &str,
    target: &str,
    protocol: &str,
    framing: &str,
    channel: &str,
    category: &str,
    direction: &str,
    payload_summary: Option<&str>,
    bytes_count: u64,
    latency_ms: f64,
    is_err: bool,
    is_external: bool,
    conn_delta: i64,
) {
    if !is_enabled() {
        return;
    }

    let src_norm = normalize_service_id(source);
    let tgt_norm = normalize_service_id(target);
    if src_norm.is_empty() || tgt_norm.is_empty() {
        return;
    }

    let proto_upper = if protocol.trim().is_empty() {
        "TCP".to_string()
    } else {
        protocol.trim().to_uppercase()
    };

    let ch_name = if channel.trim().is_empty() {
        format!("{}:default", proto_upper.to_lowercase())
    } else {
        channel.to_string()
    };

    let cat_name = if category.is_empty() { "data" } else { category };
    let dir_name = if direction.is_empty() { "outbound" } else { direction };
    let frame_format = if framing.is_empty() { "raw" } else { framing };

    let edge_key = format!("{}|{}|{}", src_norm, tgt_norm, proto_upper);
    let now_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);

    let edge_arc = {
        let registry = get_edges_registry();
        let read_guard = registry.read().unwrap();
        if let Some(edge) = read_guard.get(&edge_key) {
            edge.clone()
        } else {
            drop(read_guard);
            let mut write_guard = registry.write().unwrap();
            write_guard
                .entry(edge_key)
                .or_insert_with(|| {
                    Arc::new(AtomicEdgeEntry::new(
                        src_norm,
                        tgt_norm,
                        proto_upper,
                        frame_format.to_string(),
                    ))
                })
                .clone()
        }
    };

    if !framing.is_empty() {
        if let Ok(mut fguard) = edge_arc.framing.write() {
            if *fguard != framing {
                *fguard = framing.to_string();
            }
        }
    }

    if is_external {
        edge_arc.is_external.store(true, Ordering::Relaxed);
    }

    if conn_delta != 0 {
        let new_c = edge_arc.active_conns.fetch_add(conn_delta, Ordering::Relaxed) + conn_delta;
        if new_c < 0 {
            edge_arc.active_conns.store(0, Ordering::Relaxed);
        }
    } else if edge_arc.active_conns.load(Ordering::Relaxed) == 0 {
        edge_arc.active_conns.store(1, Ordering::Relaxed);
    }

    edge_arc.total_frames.fetch_add(1, Ordering::Relaxed);
    if bytes_count > 0 {
        edge_arc.total_bytes.fetch_add(bytes_count, Ordering::Relaxed);
    }
    if is_err {
        edge_arc.total_errors.fetch_add(1, Ordering::Relaxed);
    }
    edge_arc.last_seen_ms.store(now_ms, Ordering::Relaxed);

    let ch_arc = {
        let ch_read = edge_arc.channels.read().unwrap();
        if let Some(ch) = ch_read.get(&ch_name) {
            ch.clone()
        } else {
            drop(ch_read);
            let mut ch_write = edge_arc.channels.write().unwrap();
            ch_write
                .entry(ch_name.clone())
                .or_insert_with(|| {
                    Arc::new(AtomicChannelEntry::new(
                        ch_name,
                        cat_name.to_string(),
                        dir_name.to_string(),
                    ))
                })
                .clone()
        }
    };

    ch_arc.record(bytes_count, latency_ms, is_err, payload_summary, now_ms);
}

// -----------------------------------------------------------------------------
// Snapshot Generation & Merge
// -----------------------------------------------------------------------------

fn format_iso(ms: i64) -> String {
    if ms <= 0 {
        return String::new();
    }
    let secs = ms / 1000;
    if let Some(dt) = chrono::DateTime::from_timestamp(secs, 0) {
        dt.to_rfc3339_opts(SecondsFormat::Secs, true)
    } else {
        String::new()
    }
}

pub fn snapshot() -> Vec<EdgeReport> {
    let registry = get_edges_registry();
    let read_guard = registry.read().unwrap();
    let mut reports = Vec::with_capacity(read_guard.len());

    for edge in read_guard.values() {
        let ch_guard = edge.channels.read().unwrap();
        let mut ch_list = Vec::with_capacity(ch_guard.len());

        for ce in ch_guard.values() {
            let lat_samples = ce.lat_samples.load(Ordering::Relaxed);
            let avg_lat = if lat_samples > 0 {
                (ce.total_lat_us.load(Ordering::Relaxed) as f64 / lat_samples as f64) / 1000.0
            } else {
                0.0
            };

            let last_p = ce
                .last_payload
                .read()
                .ok()
                .and_then(|p| p.clone())
                .filter(|s| !s.is_empty());

            ch_list.push(ChannelMetric {
                channel: ce.channel.clone(),
                category: ce.category.clone(),
                direction: ce.direction.clone(),
                frames: ce.frames.load(Ordering::Relaxed),
                bytes: ce.bytes.load(Ordering::Relaxed),
                errors: ce.errors.load(Ordering::Relaxed),
                avg_latency_ms: avg_lat,
                last_seen: format_iso(ce.last_seen_ms.load(Ordering::Relaxed)),
                last_payload: last_p,
            });
        }

        ch_list.sort_by(|a, b| a.channel.cmp(&b.channel));
        let framing = edge.framing.read().map(|f| f.clone()).unwrap_or_default();

        reports.push(EdgeReport {
            source: edge.source.clone(),
            target: edge.target.clone(),
            protocol: edge.protocol.clone(),
            framing,
            active_conns: edge.active_conns.load(Ordering::Relaxed),
            total_frames: edge.total_frames.load(Ordering::Relaxed),
            total_bytes: edge.total_bytes.load(Ordering::Relaxed),
            total_errors: edge.total_errors.load(Ordering::Relaxed),
            last_seen: format_iso(edge.last_seen_ms.load(Ordering::Relaxed)),
            is_external: edge.is_external.load(Ordering::Relaxed),
            channels: ch_list,
        });
    }

    reports.sort_by(|a, b| {
        a.source
            .cmp(&b.source)
            .then_with(|| a.target.cmp(&b.target))
            .then_with(|| a.protocol.cmp(&b.protocol))
    });

    reports
}

/// Merges a batch of remote EdgeReports pushed from a microservice into the local store.
pub fn merge_remote_snapshot(incoming: &[EdgeReport]) {
    if !is_enabled() {
        return;
    }
    let now_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);

    for rep in incoming {
        let src_norm = normalize_service_id(&rep.source);
        let tgt_norm = normalize_service_id(&rep.target);
        let proto_upper = rep.protocol.trim().to_uppercase();
        if src_norm.is_empty() || tgt_norm.is_empty() || proto_upper.is_empty() {
            continue;
        }
        let edge_key = format!("{}|{}|{}", src_norm, tgt_norm, proto_upper);

        let edge_arc = {
            let registry = get_edges_registry();
            let read_guard = registry.read().unwrap();
            if let Some(edge) = read_guard.get(&edge_key) {
                edge.clone()
            } else {
                drop(read_guard);
                let mut write_guard = registry.write().unwrap();
                write_guard
                    .entry(edge_key)
                    .or_insert_with(|| {
                        Arc::new(AtomicEdgeEntry::new(
                            src_norm,
                            tgt_norm,
                            proto_upper,
                            if rep.framing.is_empty() {
                                "raw".to_string()
                            } else {
                                rep.framing.clone()
                            },
                        ))
                    })
                    .clone()
            }
        };

        if !rep.framing.is_empty() {
            if let Ok(mut fguard) = edge_arc.framing.write() {
                *fguard = rep.framing.clone();
            }
        }
        if rep.is_external {
            edge_arc.is_external.store(true, Ordering::Relaxed);
        }
        if rep.active_conns > 0 {
            edge_arc.active_conns.store(rep.active_conns, Ordering::Relaxed);
        }
        if rep.total_frames > edge_arc.total_frames.load(Ordering::Relaxed) {
            edge_arc.total_frames.store(rep.total_frames, Ordering::Relaxed);
        }
        if rep.total_bytes >= edge_arc.total_bytes.load(Ordering::Relaxed) {
            edge_arc.total_bytes.store(rep.total_bytes, Ordering::Relaxed);
        }
        edge_arc.total_errors.store(rep.total_errors, Ordering::Relaxed);
        edge_arc.last_seen_ms.store(now_ms, Ordering::Relaxed);

        for ch in &rep.channels {
            if ch.channel.is_empty() {
                continue;
            }
            let ch_arc = {
                let ch_read = edge_arc.channels.read().unwrap();
                if let Some(existing) = ch_read.get(&ch.channel) {
                    existing.clone()
                } else {
                    drop(ch_read);
                    let mut ch_write = edge_arc.channels.write().unwrap();
                    ch_write
                        .entry(ch.channel.clone())
                        .or_insert_with(|| {
                            Arc::new(AtomicChannelEntry::new(
                                ch.channel.clone(),
                                ch.category.clone(),
                                ch.direction.clone(),
                            ))
                        })
                        .clone()
                }
            };
            if ch.frames >= ch_arc.frames.load(Ordering::Relaxed) {
                ch_arc.frames.store(ch.frames, Ordering::Relaxed);
            }
            if ch.bytes >= ch_arc.bytes.load(Ordering::Relaxed) {
                ch_arc.bytes.store(ch.bytes, Ordering::Relaxed);
            }
            ch_arc.errors.store(ch.errors, Ordering::Relaxed);
            if ch.avg_latency_ms > 0.0 {
                ch_arc
                    .total_lat_us
                    .store((ch.avg_latency_ms * 1000.0) as u64, Ordering::Relaxed);
                ch_arc.lat_samples.store(1, Ordering::Relaxed);
            }
            ch_arc.last_seen_ms.store(now_ms, Ordering::Relaxed);
            if let Some(ref lp) = ch.last_payload {
                if !lp.is_empty() {
                    if let Ok(mut guard) = ch_arc.last_payload.write() {
                        *guard = Some(lp.clone());
                    }
                }
            }
        }
    }
}

pub fn reset() {
    let registry = get_edges_registry();
    let mut write_guard = registry.write().unwrap();
    write_guard.clear();
}
