// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Defines the unified serialization interface for binary and text encoding formats.
//
// DATA FLOW:
// Domain Objects <-> Serializer (JSON, MsgPack) <-> Byte Payloads
//
// KEY PARAMETERS:
// - Marshal / Unmarshal: Bidirectional conversion methods.
// -----------------------------------------------------------------------------

package serializers

// Serializer manages transforming generic structs to line formats.
//
// Implemented Providers:
// - JSON: Standard human-readable interchange.
// - Bin (MsgPack): High-performance cross-language binary serialization.
type Serializer interface {
	Marshal(data interface{}) ([]byte, error)
	Unmarshal(data []byte, ptr interface{}) error
}
