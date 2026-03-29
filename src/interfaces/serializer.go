package interfaces

// ISerializer manages transforming generic structs to line formats
type ISerializer interface {
	Marshal(data interface{}) ([]byte, error)
	Unmarshal(data []byte, ptr interface{}) error
}
