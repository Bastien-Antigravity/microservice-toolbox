// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Defines standard market data domain models (MarketEvent, OHLCV, Signal) across the fleet.
//
// DATA FLOW:
// Market Feed -> Serialization -> Business Models -> Strategy Engines
//
// KEY PARAMETERS:
// - MarketEvent: High-resolution market tick or event packet.
// - OHLCV: Standard open-high-low-close-volume candlestick record.
// - Signal: Trading signal event emitted by analytical services.
// -----------------------------------------------------------------------------

use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::fmt;

// -----------------------------------------------------------------------------
// RFC 4648 Base64 Payload Codec (JSON <-> Base64 String; Binary <-> Raw Bytes)
// -----------------------------------------------------------------------------

mod payload_base64 {
    use super::*;
    use serde::de::{self, SeqAccess, Visitor};

    const B64_TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    pub fn encode(input: &[u8]) -> String {
        let mut out = String::with_capacity(input.len().div_ceil(3) * 4);
        for chunk in input.chunks(3) {
            let b0 = chunk[0] as usize;
            let b1 = if chunk.len() > 1 { chunk[1] as usize } else { 0 };
            let b2 = if chunk.len() > 2 { chunk[2] as usize } else { 0 };
            let triple = (b0 << 16) | (b1 << 8) | b2;
            out.push(B64_TABLE[(triple >> 18) & 0x3F] as char);
            out.push(B64_TABLE[(triple >> 12) & 0x3F] as char);
            out.push(if chunk.len() > 1 { B64_TABLE[(triple >> 6) & 0x3F] as char } else { '=' });
            out.push(if chunk.len() > 2 { B64_TABLE[triple & 0x3F] as char } else { '=' });
        }
        out
    }

    pub fn decode(input: &str) -> Result<Vec<u8>, String> {
        let clean: Vec<u8> = input.bytes().filter(|b| !b.is_ascii_whitespace()).collect();
        if clean.is_empty() {
            return Ok(Vec::new());
        }
        if clean.len() % 4 != 0 {
            return Err("invalid base64 length".to_string());
        }
        let val = |c: u8| -> Result<u8, String> {
            match c {
                b'A'..=b'Z' => Ok(c - b'A'),
                b'a'..=b'z' => Ok(c - b'a' + 26),
                b'0'..=b'9' => Ok(c - b'0' + 52),
                b'+' => Ok(62),
                b'/' => Ok(63),
                _ => Err(format!("invalid base64 character: {}", c as char)),
            }
        };
        let mut out = Vec::with_capacity((clean.len() / 4) * 3);
        for chunk in clean.chunks_exact(4) {
            let v0 = val(chunk[0])? as u32;
            let v1 = val(chunk[1])? as u32;
            let pad2 = chunk[2] == b'=';
            let pad3 = chunk[3] == b'=';
            let v2 = if pad2 { 0 } else { val(chunk[2])? as u32 };
            let v3 = if pad3 { 0 } else { val(chunk[3])? as u32 };
            let triple = (v0 << 18) | (v1 << 12) | (v2 << 6) | v3;
            out.push(((triple >> 16) & 0xFF) as u8);
            if !pad2 {
                out.push(((triple >> 8) & 0xFF) as u8);
            }
            if !pad3 {
                out.push((triple & 0xFF) as u8);
            }
        }
        Ok(out)
    }

    pub fn serialize<S: Serializer>(bytes: &Vec<u8>, serializer: S) -> Result<S::Ok, S::Error> {
        if serializer.is_human_readable() {
            serializer.serialize_str(&encode(bytes))
        } else {
            serializer.serialize_bytes(bytes)
        }
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Vec<u8>, D::Error> {
        struct PayloadVisitor;
        impl<'de> Visitor<'de> for PayloadVisitor {
            type Value = Vec<u8>;

            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("a base64 string or byte buffer")
            }

            fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
                decode(v).map_err(de::Error::custom)
            }

            fn visit_bytes<E: de::Error>(self, v: &[u8]) -> Result<Self::Value, E> {
                Ok(v.to_vec())
            }

            fn visit_byte_buf<E: de::Error>(self, v: Vec<u8>) -> Result<Self::Value, E> {
                Ok(v)
            }

            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
                let mut vec = Vec::with_capacity(seq.size_hint().unwrap_or(0));
                while let Some(b) = seq.next_element()? {
                    vec.push(b);
                }
                Ok(vec)
            }
        }

        if deserializer.is_human_readable() {
            deserializer.deserialize_any(PayloadVisitor)
        } else {
            deserializer.deserialize_byte_buf(PayloadVisitor)
        }
    }
}

// -----------------------------------------------------------------------------
// Market Event Standard (L1/L2)
// -----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub enum MarketEventType {
    #[serde(rename = "trade")]
    Trade,
    #[serde(rename = "quote")]
    Quote,
    #[serde(rename = "orderbookSnapshot")]
    OrderBookSnapshot,
    #[serde(rename = "orderbookUpdate")]
    OrderBookUpdate,
    #[serde(rename = "heartbeat")]
    Heartbeat,
    #[serde(rename = "control")]
    Control,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketEvent {
    pub event_id: String,
    pub symbol: String,
    pub exchange: String,
    pub timestamp: u64,
    #[serde(rename = "type")]
    pub event_type: MarketEventType,
    #[serde(with = "payload_base64")]
    pub payload: Vec<u8>, // Serialized Trade, Quote, or OrderBook (Base64 in JSON)
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Aggressor {
    Buy,
    Sell,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Trade {
    pub price: f64,
    pub size: f64,
    pub aggressor: Aggressor,
    pub trade_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Quote {
    pub bid_price: f64,
    pub bid_size: f64,
    pub ask_price: f64,
    pub ask_size: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OrderBookLevel {
    pub price: f64,
    pub size: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OrderBook {
    pub bids: Vec<OrderBookLevel>,
    pub asks: Vec<OrderBookLevel>,
}

// -----------------------------------------------------------------------------
// OHLCV Standard (Time-Series)
// -----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OHLCV {
    pub symbol: String,
    pub interval: String,
    pub timestamp: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub vwap: f64,
    pub trades: u32,
}

// -----------------------------------------------------------------------------
// Signal Standard (Trading Strategy)
// -----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum SignalType {
    Buy,
    Sell,
    Exit,
    Neutral,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Signal {
    pub source: String,
    pub symbol: String,
    pub timestamp: u64,
    #[serde(rename = "type")]
    pub signal_type: SignalType,
    pub strength: f32,
    pub price: f64,
    pub metadata: String,
}
