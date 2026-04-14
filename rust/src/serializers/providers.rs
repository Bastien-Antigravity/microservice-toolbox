use serde::{Serialize, de::DeserializeOwned};
use serde_json;
use rmp_serde;
use crate::serializers::serializer::Serializer;

/// JsonSerializer implements Serializer natively over JSON.
pub struct JsonSerializer;

pub enum SerializerEnum {
    Json(JsonSerializer),
    Bin(BinSerializer),
}

impl SerializerEnum {
    pub fn new_json() -> Self {
        SerializerEnum::Json(JsonSerializer)
    }

    pub fn new_bin() -> Self {
        SerializerEnum::Bin(BinSerializer)
    }
}

impl Serializer for SerializerEnum {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>> {
        match self {
            SerializerEnum::Json(s) => s.marshal(data),
            SerializerEnum::Bin(s) => s.marshal(data),
        }
    }

    fn unmarshal<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error + Send + Sync>> {
        match self {
            SerializerEnum::Json(s) => s.unmarshal(data),
            SerializerEnum::Bin(s) => s.unmarshal(data),
        }
    }
}

impl JsonSerializer {
    pub fn new() -> SerializerEnum {
        SerializerEnum::new_json()
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

/// BinSerializer implements Serializer using msgpack encoding.
/// Note: matched with Go's 'BinSerializer' using msgpack.
pub struct BinSerializer;

impl BinSerializer {
    pub fn new() -> SerializerEnum {
        SerializerEnum::new_bin()
    }
}

impl Serializer for BinSerializer {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>> {
        rmp_serde::to_vec(data).map_err(|e| e.into())
    }

    fn unmarshal<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error + Send + Sync>> {
        rmp_serde::from_slice(data).map_err(|e| e.into())
    }
}

pub fn new_json_serializer() -> SerializerEnum {
    SerializerEnum::new_json()
}

pub fn new_bin_serializer() -> SerializerEnum {
    SerializerEnum::new_bin()
}
