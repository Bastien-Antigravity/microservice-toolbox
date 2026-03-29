package serializers

import (
	"encoding/json"
	"fmt"

	"github.com/Bastien-Antigravity/message-serializers/src/interfaces"
)

// JSONSerializer implements interfaces.ISerializer natively over JSON
type JSONSerializer struct{}

// NewJSONSerializer creates a new instance of the JSON serializer.
func NewJSONSerializer() interfaces.ISerializer {
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
