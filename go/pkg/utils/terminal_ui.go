package utils

import (
	"fmt"
	"time"
)

// PrintInternalLog prints a formatted internal log message
func PrintInternalLog(level, module, filename, line, message string) {
	timestamp := time.Now().Format("2006-01-02T15:04:05.000000000Z")
	hostname := GetHostname()

	// Colorize level
	color := ""
	switch level {
	case "DEBUG":
		color = "\x1b[36m"
	case "INFO", "LOGON", "LOGOUT":
		color = "\x1b[32m"
	case "WARNING":
		color = "\x1b[33m"
	case "ERROR", "CRITICAL":
		color = "\x1b[31m"
	}
	coloredLevel := fmt.Sprintf("%s%-10s\x1b[0m", color, truncate(level, 10))

	// Fixed column format: 33-12-15-10-20-25-6 message
	fmt.Printf(
		"%-33s %-12s %-15s %s %-20s %-25s %-6s %s\n",
		timestamp,
		truncate(hostname, 12),
		truncate("microservice-toolbox", 15),
		coloredLevel,
		truncate(filename, 20),
		truncate(module, 25),
		truncate(line, 6),
		message,
	)
}

func truncate(s string, maxLen int) string {
	if len(s) > maxLen {
		return s[:maxLen]
	}
	return s
}
