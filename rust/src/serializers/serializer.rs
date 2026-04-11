use serde::{Serialize, de::DeserializeOwned};

/// Serializer trait manages transforming generic structs to line formats.
pub trait Serializer {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>>;
    fn unmarshal<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error + Send + Sync>>;
}
