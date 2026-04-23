package conn_manager

import (
	"testing"
	"time"
)

func TestStrategies(t *testing.T) {
	// 1. Test Critical Strategy
	nmCritical := NewCriticalStrategy(nil)
	if nmCritical.MaxRetries != -1 {
		t.Errorf("CriticalStrategy should have infinite retries, got %d", nmCritical.MaxRetries)
	}

	// 2. Test Standard Strategy
	nmStandard := NewStandardStrategy(nil)
	if nmStandard.MaxRetries != 10 {
		t.Errorf("StandardStrategy should have 10 retries, got %d", nmStandard.MaxRetries)
	}

	// 3. Test Performance Strategy
	nmPerf := NewPerformanceStrategy(nil)
	if nmPerf.BaseDelay != 100*time.Millisecond {
		t.Errorf("PerformanceStrategy should have 100ms base delay, got %v", nmPerf.BaseDelay)
	}
}

func TestUnifiedConnect(t *testing.T) {
	ip := "127.0.0.1"
	port := "9999"
	publicIP := ""
	profile := "test"

	// 1. Test NonBlocking: should return immediately
	nm1 := NewNetworkManager(2, 10, 50, 50, 1.0, 0.0)
	start := time.Now()
	mc1 := nm1.Connect(&ip, &port, &publicIP, profile, ModeNonBlocking)
	elapsed := time.Since(start)
	if elapsed > 50*time.Millisecond {
		t.Errorf("Connect(ModeNonBlocking) took too long: %v", elapsed)
	}
	_ = mc1.Close()

	// 2. Test Blocking with limited retries: should error out and return mc with nil conn
	nm2 := NewNetworkManager(2, 10, 50, 50, 1.0, 0.0)
	errorCount2 := 0
	nm2.OnError = func(attempt int, err error, source string, msg string) {
		errorCount2++
	}

	mc2 := nm2.Connect(&ip, &port, &publicIP, profile, ModeBlocking)
	if errorCount2 != 2 {
		t.Errorf("Expected 2 retries for ModeBlocking, got %d", errorCount2)
	}
	_ = mc2.Close()

	// 3. Test Indefinite: should continue retrying.
	nm3 := NewNetworkManager(2, 10, 50, 50, 1.0, 0.0)
	errorCount3 := 0
	nm3.OnError = func(attempt int, err error, source string, msg string) {
		errorCount3++
	}

	// We'll run it in background because it blocks indefinitely
	go nm3.Connect(&ip, &port, &publicIP, profile, ModeIndefinite)

	// Wait enough time for > 2 retries
	time.Sleep(100 * time.Millisecond)
	if errorCount3 <= 2 {
		t.Errorf("Expected Indefinite mode to exceed MaxRetries(2), but only got %d errors", errorCount3)
	}
}
