package serializers

import (
	"encoding/json"
	"fmt"

	"github.com/vmihailenco/msgpack/v5"
)

// -----------------------------------------------------------------------------
// JSONSerializer implements Serializer natively over JSON.
type JSONSerializer struct{}

func NewJSONSerializer() Serializer {
	return &JSONSerializer{}
}

func (s *JSONSerializer) Marshal(data interface{}) ([]byte, error) {
	b, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("json marshal error: %w", err)
	}
	return b, nil
}

func (s *JSONSerializer) Unmarshal(data []byte, ptr interface{}) error {
	if err := json.Unmarshal(data, ptr); err != nil {
		return fmt.Errorf("json unmarshal error: %w", err)
	}
	return nil
}

// -----------------------------------------------------------------------------
// -----------------------------------------------------------------------------
// BinSerializer implements Serializer using msgpack encoding.
type BinSerializer struct{}

func NewBinSerializer() Serializer {
	return &BinSerializer{}
}

func (g *BinSerializer) Marshal(obj interface{}) ([]byte, error) {
	b, err := msgpack.Marshal(obj)
	if err != nil {
		return nil, fmt.Errorf("msgpack marshal error: %w", err)
	}
	return b, nil
}

func (g *BinSerializer) Unmarshal(data []byte, obj interface{}) error {
	if err := msgpack.Unmarshal(data, obj); err != nil {
		return fmt.Errorf("msgpack unmarshal error: %w", err)
	}
	return nil
}
