package serializers

import (
	"bytes"
	"encoding/gob"
	"fmt"

	"github.com/Bastien-Antigravity/message-serializers/src/interfaces"
)

// -----------------------------------------------------------------------------

type BinSerializer struct{}

// -----------------------------------------------------------------------------

// NewBinSerializer creates a new instance of the Gob serializer.
func NewBinSerializer() interfaces.ISerializer {
	return &BinSerializer{}
}

// -----------------------------------------------------------------------------

func (g *BinSerializer) Marshal(obj interface{}) ([]byte, error) {
	var buf bytes.Buffer
	enc := gob.NewEncoder(&buf)

	if err := enc.Encode(obj); err != nil {
		return nil, fmt.Errorf("gob marshal error: %w", err)
	}

	return buf.Bytes(), nil
}

// -----------------------------------------------------------------------------

// Unmarshal converts a Gob byte array back into the target object.
func (g *BinSerializer) Unmarshal(data []byte, obj interface{}) error {
	buf := bytes.NewBuffer(data)
	dec := gob.NewDecoder(buf)

	if err := dec.Decode(obj); err != nil {
		return fmt.Errorf("gob unmarshal error: %w", err)
	}
	return nil
}
