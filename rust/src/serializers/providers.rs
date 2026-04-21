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
    pub fn new() -> Self {
        JsonSerializer
    }
}

impl Default for JsonSerializer {
    fn default() -> Self {
        Self::new()
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
    pub fn new() -> Self {
        BinSerializer
    }
}

impl Default for BinSerializer {
    fn default() -> Self {
        Self::new()
    }
}

impl Serializer for BinSerializer {
    fn marshal<T: Serialize>(&self, data: &T) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>> {
        rmp_serde::to_vec_named(data).map_err(|e| e.into())
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde::{Deserialize, Serialize};

    #[derive(Serialize, Deserialize, Debug, PartialEq)]
    struct TestData {
        name: String,
        value: i32,
    }

    #[test]
    fn test_serializers_roundtrip() {
        let data = TestData {
            name: "Toolbox".to_string(),
            value: 42,
        };

        let serializers = vec![
            SerializerEnum::new_json(),
            SerializerEnum::new_bin(),
        ];

        for s in serializers {
            // Marshal
            let encoded = s.marshal(&data).expect("Marshal failed");
            assert!(!encoded.is_empty());

            // Unmarshal
            let decoded: TestData = s.unmarshal(&encoded).expect("Unmarshal failed");
            assert_eq!(data, decoded);
        }
    }
}
