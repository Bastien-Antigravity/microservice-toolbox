package serializers

import (
	"bytes"
	"encoding/gob"
	"encoding/json"
	"fmt"
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
// BinSerializer implements Serializer using Go's gob encoding.
type BinSerializer struct{}

func NewBinSerializer() Serializer {
	return &BinSerializer{}
}

func (g *BinSerializer) Marshal(obj interface{}) ([]byte, error) {
	var buf bytes.Buffer
	enc := gob.NewEncoder(&buf)
	if err := enc.Encode(obj); err != nil {
		return nil, fmt.Errorf("gob marshal error: %w", err)
	}
	return buf.Bytes(), nil
}

func (g *BinSerializer) Unmarshal(data []byte, obj interface{}) error {
	buf := bytes.NewBuffer(data)
	dec := gob.NewDecoder(buf)
	if err := dec.Decode(obj); err != nil {
		return fmt.Errorf("gob unmarshal error: %w", err)
	}
	return nil
}
