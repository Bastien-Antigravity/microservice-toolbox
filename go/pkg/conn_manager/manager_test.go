package conn_manager

import (
	"testing"
	"time"
)

func TestConnectNonBlocking(t *testing.T) {
	nm := NewNetworkManager(5, 100, 1000, 500, 2.0, 0.0)
	
	ip := "127.0.0.1"
	port := "9999" // Non-existent port
	publicIP := ""
	profile := "raw"

	start := time.Now()
	mc := nm.ConnectNonBlocking(&ip, &port, &publicIP, profile)
	elapsed := time.Since(start)
	
	if elapsed > 100*time.Millisecond {
		t.Errorf("ConnectNonBlocking took too long: %v", elapsed)
	}
	
	if mc == nil {
		t.Error("ConnectNonBlocking returned nil")
	}

	mc.Close()
}

func TestOnErrorUnifiedHook(t *testing.T) {
	errorCount := 0
	lastAttempt := 0
	
	nm := NewNetworkManager(2, 10, 100, 50, 1.0, 0.0)
	nm.OnError = func(attempt int, err error, source string, msg string) {
		errorCount++
		lastAttempt = attempt
	}
	
	ip := "127.0.0.1"
	port := "9999"
	publicIP := ""
	profile := "test"
	
	_, err := nm.ConnectWithRetry(&ip, &port, &publicIP, profile)
	
	if err == nil {
		t.Error("Expected connection failure to non-existent port")
	}
	
	if errorCount != 2 {
		t.Errorf("Expected 2 error callbacks, got %d", errorCount)
	}
	
	if lastAttempt != 2 {
		t.Errorf("Expected last attempt to be 2, got %d", lastAttempt)
	}
}
