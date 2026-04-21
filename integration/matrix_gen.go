package main

import (
	"fmt"
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

	data := IntegrationData{Name: "Integration", Value: 100}
	
	b, err := s.Marshal(data)
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal error: %v\n", err)
		os.Exit(1)
	}
	
	os.Stdout.Write(b)
}
