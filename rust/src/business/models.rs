use serde::{Deserialize, Serialize};

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
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketEvent {
    pub event_id: String,
    pub symbol: String,
    pub exchange: String,
    pub timestamp: u64,
    #[serde(rename = "type")]
    pub event_type: MarketEventType,
    pub payload: Vec<u8>, // Serialized Trade, Quote, or OrderBook
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
