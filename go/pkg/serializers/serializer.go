package serializers

// Serializer manages transforming generic structs to line formats.
type Serializer interface {
	Marshal(data interface{}) ([]byte, error)
	Unmarshal(data []byte, ptr interface{}) error
}
