package main

import (
	"fmt"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	"os"
)

func main() {
    // Faking arguments
    os.Args = []string{"main", "--host=localhost"}
	cfg, err := config.LoadConfig("test", nil)
	if err != nil {
		panic(err)
	}
    
	fmt.Printf("Capabilities: %+v\n", cfg.Config.Capabilities)
	fmt.Printf("Common Name: %s\n", cfg.Config.Common.Name)
}
