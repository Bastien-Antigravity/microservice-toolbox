// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Helper utilities and conversion routines for core business domain models.
//
// DATA FLOW:
// Raw Market Data -> Business Helpers -> Validated Domain Structures
//
// KEY PARAMETERS:
// - serialize / deserialize: JSON serialization helpers matching Go & Python.
// - wrap_market_event: Wraps typed domain payloads into a MarketEvent envelope.
// - system_timestamp: Returns current UTC Unix timestamp in milliseconds.
// -----------------------------------------------------------------------------

use serde::{Serialize, de::DeserializeOwned};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::business::models::{MarketEvent, MarketEventType};

// -----------------------------------------------------------------------------

/// Converts a business object into a JSON byte array.
pub fn serialize<T: Serialize>(v: &T) -> Result<Vec<u8>, serde_json::Error> {
    serde_json::to_vec(v)
}

// -----------------------------------------------------------------------------

/// Converts a JSON byte array into the target business object.
pub fn deserialize<T: DeserializeOwned>(data: &[u8]) -> Result<T, serde_json::Error> {
    serde_json::from_slice(data)
}

// -----------------------------------------------------------------------------

/// Creates a MarketEvent envelope for a typed business payload.
pub fn wrap_market_event<T: Serialize>(
    symbol: &str,
    exchange: &str,
    event_type: MarketEventType,
    payload: &T,
) -> Result<MarketEvent, serde_json::Error> {
    let serialized_payload = serialize(payload)?;
    let ts = system_timestamp();

    Ok(MarketEvent {
        event_id: format!("{}-{}", symbol, ts),
        symbol: symbol.to_string(),
        exchange: exchange.to_string(),
        timestamp: ts,
        event_type,
        payload: serialized_payload,
    })
}

// -----------------------------------------------------------------------------

/// Returns the current unix timestamp in milliseconds.
pub fn system_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

