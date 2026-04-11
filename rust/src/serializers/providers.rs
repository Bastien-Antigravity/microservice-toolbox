use serde::{Serialize, de::DeserializeOwned};
use serde_json;
use bincode;
use crate::serializers::serializer::Serializer;

/// JsonSerializer implements Serializer natively over JSON.
pub struct JsonSerializer;

impl JsonSerializer {
    pub fn new() -> Box<dyn Serializer> {
        Box::new(JsonSerializer)
    }
}

impl Serializer for JsonSerializer {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>> {
        serde_json::to_vec(data).map_err(|e| e.into())
    }

    fn unmarshal<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error + Send + Sync>> {
        serde_json::from_slice(data).map_err(|e| e.into())
    }
}

/// BinSerializer implements Serializer using bincode encoding.
/// Note: matched with Go's 'BinSerializer' but using bincode as gob equivalent.
pub struct BinSerializer;

impl BinSerializer {
    pub fn new() -> Box<dyn Serializer> {
        Box::new(BinSerializer)
    }
}

impl Serializer for BinSerializer {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>> {
        bincode::serialize(data).map_err(|e| e.into())
    }

    fn unmarshal<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error + Send + Sync>> {
        bincode::deserialize(data).map_err(|e| e.into())
    }
}

pub fn new_json_serializer() -> Box<dyn Serializer> {
    Box::new(JsonSerializer)
}

pub fn new_bin_serializer() -> Box<dyn Serializer> {
    Box::new(BinSerializer)
}
