// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: test_business_models.rs.
//
// DATA FLOW:
// Callers -> test_business_models.rs -> Processed Output
//
// KEY PARAMETERS:
// - Standard module parameters.
// -----------------------------------------------------------------------------

use microservice_toolbox::business::*;
use serde_json;

#[test]
fn test_market_event_serialization_and_base64_parity() {
    let trade = Trade {
        price: 100.50,
        size: 1.5,
        aggressor: Aggressor::Buy,
        trade_id: "T12345".to_string(),
    };

    let event = wrap_market_event("BTC/USD", "Binance", MarketEventType::Trade, &trade).unwrap();
    assert_eq!(event.symbol, "BTC/USD");

    let serialized = serde_json::to_string(&event).unwrap();
    assert!(serialized.contains("\"type\":\"trade\""));
    assert!(serialized.contains("\"symbol\":\"BTC/USD\""));
    // Payload must serialize as a Base64 string in JSON (not an integer array)
    let raw_val: serde_json::Value = serde_json::from_str(&serialized).unwrap();
    assert!(raw_val["payload"].is_string(), "expected Base64 string payload, got: {}", raw_val["payload"]);

    let wire_bytes = serialize(&event).unwrap();
    let deserialized: MarketEvent = deserialize(&wire_bytes).unwrap();
    assert_eq!(event, deserialized);

    let decoded_trade: Trade = deserialize(&deserialized.payload).unwrap();
    assert_eq!(decoded_trade, trade);
}

#[test]
fn test_control_event_and_orderbook_roundtrip() {
    let ob = OrderBook {
        bids: vec![OrderBookLevel { price: 100.0, size: 2.5 }],
        asks: vec![OrderBookLevel { price: 101.0, size: 1.5 }],
    };
    let ev = wrap_market_event("ETH/USD", "Coinbase", MarketEventType::Control, &ob).unwrap();
    let bytes = serialize(&ev).unwrap();
    let decoded: MarketEvent = deserialize(&bytes).unwrap();
    assert_eq!(decoded.event_type, MarketEventType::Control);
    let decoded_ob: OrderBook = deserialize(&decoded.payload).unwrap();
    assert_eq!(decoded_ob, ob);
    assert!(system_timestamp() > 0);
}

#[test]
fn test_signal_serialization() {
    let signal = Signal {
        source: "strategy-a".to_string(),
        symbol: "ETH/USD".to_string(),
        timestamp: 1625097600,
        signal_type: SignalType::Buy,
        strength: 0.85,
        price: 2500.0,
        metadata: "{\"reason\": \"rsi_oversold\"}".to_string(),
    };

    let serialized = serde_json::to_string(&signal).unwrap();
    assert!(serialized.contains("\"type\":\"buy\""));

    let deserialized: Signal = serde_json::from_str(&serialized).unwrap();
    assert_eq!(signal, deserialized);
}
