package main

import (
	"fmt"
	"os"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
)

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: expansion_check <profile> <key>")
		os.Exit(1)
	}

	profile := os.Args[1]
	key := os.Args[2]

	ac, err := config.LoadConfig(profile, nil)
	if err != nil {
		// If LoadConfig fails, it might still have loaded local overrides if they exist
		// but let's try to continue if we can.
	}

	val := ac.GetLocal(key)
	fmt.Printf("VALUE:%v", val)
}
