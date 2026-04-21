use serde::{Serialize, de::DeserializeOwned};

/// Serializer trait manages transforming generic structs to line formats.
/// 
/// Implemented Providers:
/// - JSON: Standard human-readable interchange.
/// - Bin (MsgPack): High-performance cross-language binary serialization.
pub trait Serializer {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>>;
    fn unmarshal<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error + Send + Sync>>;
}
