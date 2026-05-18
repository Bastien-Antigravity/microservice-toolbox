use microservice_toolbox::business::models::*;
use serde_json;

#[test]
fn test_market_event_serialization() {
    let event = MarketEvent {
        event_id: "123".to_string(),
        symbol: "BTC/USD".to_string(),
        exchange: "binance".to_string(),
        timestamp: 1625097600,
        event_type: MarketEventType::Trade,
        payload: vec![1, 2, 3],
    };

    let serialized = serde_json::to_string(&event).unwrap();
    assert!(serialized.contains("\"type\":\"trade\""));
    assert!(serialized.contains("\"symbol\":\"BTC/USD\""));

    let deserialized: MarketEvent = serde_json::from_str(&serialized).unwrap();
    assert_eq!(event, deserialized);
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
