package utils

import (
	"os"
)

// GetHostname returns the system hostname
func GetHostname() string {
	name, err := os.Hostname()
	if err != nil {
		return "localhost"
	}
	return name
}
