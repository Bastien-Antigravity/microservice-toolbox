package serializers

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

type TestData struct {
	Name  string `json:"name" msgpack:"name"`
	Value int    `json:"value" msgpack:"value"`
}

func TestSerializers_RoundTrip(t *testing.T) {
	data := TestData{Name: "Toolbox", Value: 42}

	serializers := []struct {
		name string
		s    Serializer
	}{
		{"JSON", NewJSONSerializer()},
		{"Bin (MsgPack)", NewBinSerializer()},
	}

	for _, tc := range serializers {
		t.Run(tc.name, func(t *testing.T) {
			// Marshal
			b, err := tc.s.Marshal(data)
			assert.NoError(t, err)
			assert.NotEmpty(t, b)

			// Unmarshal
			var decoded TestData
			err = tc.s.Unmarshal(b, &decoded)
			assert.NoError(t, err)
			assert.Equal(t, data, decoded)
		})
	}
}

func TestSerializers_Errors(t *testing.T) {
	s := NewJSONSerializer()
	
	// Unmarshal invalid data
	var data TestData
	err := s.Unmarshal([]byte("invalid json"), &data)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "json unmarshal error")

	bs := NewBinSerializer()
	err = bs.Unmarshal([]byte{0xc1}, &data) // Invalid msgpack byte
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "msgpack unmarshal error")
}
