package business

import (
	"encoding/json"
	"fmt"
	"time"
)

// Serialize converts a business object into a JSON byte array.
func Serialize(v interface{}) ([]byte, error) {
	data, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("failed to serialize business object: %w", err)
	}
	return data, nil
}

// Deserialize converts a JSON byte array into the target business object.
func Deserialize(data []byte, v interface{}) error {
	if err := json.Unmarshal(data, v); err != nil {
		return fmt.Errorf("failed to deserialize business object: %w", err)
	}
	return nil
}

// WrapMarketEvent creates a MarketEvent envelope for a payload.
func WrapMarketEvent(symbol string, exchange string, eventType MarketEventType, payload interface{}) (*MarketEvent, error) {
	serializedPayload, err := Serialize(payload)
	if err != nil {
		return nil, err
	}

	return &MarketEvent{
		EventID:   fmt.Sprintf("%s-%d", symbol, SystemTimestamp()),
		Symbol:    symbol,
		Exchange:  exchange,
		Timestamp: SystemTimestamp(),
		Type:      eventType,
		Payload:   serializedPayload,
	}, nil
}

// SystemTimestamp returns the current unix timestamp in milliseconds.
func SystemTimestamp() uint64 {
	return uint64(timeNow().UnixNano() / 1e6)
}

// timeNow is a mockable time function for testing.
var timeNow = time.Now
