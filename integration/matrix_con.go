package main

import (
	"fmt"
	"io"
	"os"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/serializers"
)

type IntegrationData struct {
	Name  string `json:"name" msgpack:"name"`
	Value int    `json:"value" msgpack:"value"`
}

func main() {
	format := "msgpack"
	if len(os.Args) > 1 {
		format = os.Args[1]
	}

	var s serializers.Serializer
	if format == "json" {
		s = serializers.NewJSONSerializer()
	} else {
		s = serializers.NewBinSerializer()
	}

	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to read stdin: %v\n", err)
		os.Exit(1)
	}

	var decoded IntegrationData
	err = s.Unmarshal(data, &decoded)
	if err != nil {
		fmt.Fprintf(os.Stderr, "unmarshal error: %v\n", err)
		os.Exit(1)
	}

	expected := IntegrationData{Name: "Integration", Value: 100}
	if decoded.Name == expected.Name && decoded.Value == expected.Value {
		fmt.Fprintf(os.Stderr, "Go: Success (%s)\n", format)
		os.Exit(0)
	} else {
		fmt.Fprintf(os.Stderr, "Go: Data mismatch (%s). Got %+v\n", format, decoded)
		os.Exit(1)
	}
}
