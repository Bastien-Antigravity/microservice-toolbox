// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Cross-service and cross-brain mission trace correlation (X-Bastien-Mission-ID)
// for Rust microservices. Sanitizes, extracts, injects, and binds mission_id
// into structured Logger metadata.
//
// DATA FLOW:
// Inbound HTTP / NATS Header / Env -> sanitize_mission_id -> Logger::add_metadata("mission_id")
//
// KEY PARAMETERS:
// - HEADER_MISSION_ID: Canonical wire header ("X-Bastien-Mission-ID").
// - METADATA_KEY: Canonical universal-logger metadata slot ("mission_id").
// - ENV_MISSION_ID: Process environment seed ("X_BASTIEN_MISSION_ID").
// -----------------------------------------------------------------------------

use std::collections::HashMap;
use std::sync::Arc;

use crate::utils::logger::Logger;

//-----------------------------------------------------------------------------------------------

pub const HEADER_MISSION_ID: &str = "X-Bastien-Mission-ID";
pub const METADATA_KEY: &str = "mission_id";
pub const ENV_MISSION_ID: &str = "X_BASTIEN_MISSION_ID";
const MAX_MISSION_ID_LEN: usize = 128;

//-----------------------------------------------------------------------------------------------

/// Validates and trims a raw mission ID, rejecting whitespace/control characters or >128 bytes.
pub fn sanitize_mission_id(raw: &str) -> Option<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() || trimmed.len() > MAX_MISSION_ID_LEN {
        return None;
    }
    if trimmed.bytes().all(|b| (0x21..=0x7E).contains(&b)) {
        Some(trimmed.to_string())
    } else {
        None
    }
}

//-----------------------------------------------------------------------------------------------

/// Resolves X_BASTIEN_MISSION_ID from the process environment if set and valid.
pub fn resolve_env_mission_id() -> Option<String> {
    std::env::var(ENV_MISSION_ID)
        .ok()
        .and_then(|v| sanitize_mission_id(&v))
}

//-----------------------------------------------------------------------------------------------

/// Binds mission_id onto a toolbox Logger when valid.
pub fn bind_logger_mission(logger: &Arc<dyn Logger>, mission_id: &str) -> Option<String> {
    let clean = sanitize_mission_id(mission_id)?;
    logger.add_metadata(METADATA_KEY, &clean);
    Some(clean)
}

//-----------------------------------------------------------------------------------------------

/// Extracts X-Bastien-Mission-ID case-insensitively from a string header map.
pub fn extract_mission_id(headers: &HashMap<String, String>) -> Option<String> {
    if let Some(val) = headers.get(HEADER_MISSION_ID) {
        return sanitize_mission_id(val);
    }
    for (k, v) in headers {
        if k.eq_ignore_ascii_case(HEADER_MISSION_ID) {
            return sanitize_mission_id(v);
        }
    }
    None
}

//-----------------------------------------------------------------------------------------------

/// Injects X-Bastien-Mission-ID into an outbound header map if valid.
pub fn inject_mission_id(headers: &mut HashMap<String, String>, mission_id: &str) {
    if let Some(clean) = sanitize_mission_id(mission_id) {
        headers.insert(HEADER_MISSION_ID.to_string(), clean);
    }
}

//-----------------------------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mission_id_roundtrip_and_sanitize() {
        let mut hdrs = HashMap::new();
        inject_mission_id(&mut hdrs, "mission-rust-42");
        assert_eq!(
            extract_mission_id(&hdrs),
            Some("mission-rust-42".to_string())
        );
        assert_eq!(sanitize_mission_id("bad\nvalue"), None);
        assert_eq!(sanitize_mission_id("bad space"), None);
    }
}
