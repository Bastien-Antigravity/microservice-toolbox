package utils

import (
	"fmt"
)

// Logger is a structurally compatible interface with universal-logger.
// This allows microservice-toolbox to use structured logging without
// a hard dependency on the logging implementation.
type Logger interface {
	Debug(format string, args ...any)
	Info(format string, args ...any)
	Warning(format string, args ...any)
	Error(format string, args ...any)
	Critical(format string, args ...any)
	Logon(format string, args ...any)
	Logout(format string, args ...any)
	Trade(format string, args ...any)
	Schedule(format string, args ...any)
	Report(format string, args ...any)
	Stream(format string, args ...any)

	// AddMetadata adds structured tags to the logger (if supported).
	AddMetadata(key string, value string)
}

// EnsureSafeLogger returns a no-op logger if the provided one is nil.
// This is used internally by toolbox components to avoid nil pointer panics.
func EnsureSafeLogger(l Logger) Logger {
	if l == nil {
		return &noOpLogger{}
	}
	return l
}

type noOpLogger struct{}

func (n *noOpLogger) Debug(string, ...any)       {}
func (n *noOpLogger) Info(string, ...any)        {}
func (n *noOpLogger) Warning(string, ...any)     {}
func (n *noOpLogger) Error(string, ...any)       {}
func (n *noOpLogger) Critical(string, ...any)    {}
func (n *noOpLogger) Logon(string, ...any)       {}
func (n *noOpLogger) Logout(string, ...any)      {}
func (n *noOpLogger) Trade(string, ...any)       {}
func (n *noOpLogger) Schedule(string, ...any)    {}
func (n *noOpLogger) Report(string, ...any)      {}
func (n *noOpLogger) Stream(string, ...any)      {}
func (n *noOpLogger) AddMetadata(string, string) {}

// FmtLogger is a simple logger that prints to stdout, useful for debugging.
type FmtLogger struct{}

func (f *FmtLogger) Debug(fmt_str string, args ...any)   { fmt.Printf("DEBUG: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Info(fmt_str string, args ...any)    { fmt.Printf("INFO: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Warning(fmt_str string, args ...any) { fmt.Printf("WARN: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Error(fmt_str string, args ...any)   { fmt.Printf("ERROR: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Critical(fmt_str string, args ...any) {
	fmt.Printf("CRITICAL: "+fmt_str+"\n", args...)
}
func (f *FmtLogger) Logon(fmt_str string, args ...any)  { fmt.Printf("LOGON: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Logout(fmt_str string, args ...any) { fmt.Printf("LOGOUT: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Trade(fmt_str string, args ...any)  { fmt.Printf("TRADE: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Schedule(fmt_str string, args ...any) {
	fmt.Printf("SCHEDULE: "+fmt_str+"\n", args...)
}
func (f *FmtLogger) Report(fmt_str string, args ...any) { fmt.Printf("REPORT: "+fmt_str+"\n", args...) }
func (f *FmtLogger) Stream(fmt_str string, args ...any) { fmt.Printf("STREAM: "+fmt_str+"\n", args...) }
func (f *FmtLogger) AddMetadata(k string, v string)     { fmt.Printf("META: %s=%s\n", k, v) }
