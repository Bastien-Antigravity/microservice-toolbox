package business

import (
	"testing"
)

func TestMarketEventSerialization(t *testing.T) {
	trade := Trade{
		Price:     100.50,
		Size:      1.5,
		Aggressor: AggressorBuy,
		TradeID:   "T12345",
	}

	event, err := WrapMarketEvent("BTC/USD", "Binance", TypeTrade, trade)
	if err != nil {
		t.Fatalf("Failed to wrap market event: %v", err)
	}

	if event.Symbol != "BTC/USD" {
		t.Errorf("Expected symbol BTC/USD, got %s", event.Symbol)
	}

	data, err := Serialize(event)
	if err != nil {
		t.Fatalf("Failed to serialize event: %v", err)
	}

	var decodedEvent MarketEvent
	if err := Deserialize(data, &decodedEvent); err != nil {
		t.Fatalf("Failed to deserialize event: %v", err)
	}

	if decodedEvent.Type != TypeTrade {
		t.Errorf("Expected type trade, got %s", decodedEvent.Type)
	}

	var decodedTrade Trade
	if err := Deserialize(decodedEvent.Payload, &decodedTrade); err != nil {
		t.Fatalf("Failed to deserialize trade payload: %v", err)
	}

	if decodedTrade.Price != 100.50 {
		t.Errorf("Expected price 100.50, got %f", decodedTrade.Price)
	}
}

func TestOHLCVSerialization(t *testing.T) {
	bar := OHLCV{
		Symbol:    "ETH/USD",
		Interval:  "1m",
		Timestamp: 1620000000000,
		Open:      2500.0,
		High:      2510.0,
		Low:       2495.0,
		Close:     2505.0,
		Volume:    100.0,
	}

	data, err := Serialize(bar)
	if err != nil {
		t.Fatalf("Failed to serialize OHLCV: %v", err)
	}

	var decodedBar OHLCV
	if err := Deserialize(data, &decodedBar); err != nil {
		t.Fatalf("Failed to deserialize OHLCV: %v", err)
	}

	if decodedBar.Symbol != "ETH/USD" {
		t.Errorf("Expected symbol ETH/USD, got %s", decodedBar.Symbol)
	}
}

func TestSignalSerialization(t *testing.T) {
	signal := Signal{
		Source:    "technical-analysis",
		Symbol:    "SOL/USD",
		Timestamp: 1620000000000,
		Type:      SignalBuy,
		Strength:  0.85,
		Price:     150.0,
	}

	data, err := Serialize(signal)
	if err != nil {
		t.Fatalf("Failed to serialize Signal: %v", err)
	}

	var decodedSignal Signal
	if err := Deserialize(data, &decodedSignal); err != nil {
		t.Fatalf("Failed to deserialize Signal: %v", err)
	}

	if decodedSignal.Type != SignalBuy {
		t.Errorf("Expected type buy, got %s", decodedSignal.Type)
	}
}
