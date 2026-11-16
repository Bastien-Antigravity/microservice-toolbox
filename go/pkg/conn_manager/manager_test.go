// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Manages polyglot inter-service network connections with lifecycle hooks and circuit breakers.
//
// DATA FLOW:
// Service Request -> Connection Pool / ManagedConnection -> Active Inter-service Link
//
// KEY PARAMETERS:
// - connections: Active managed connections map.
// - strategies: Backoff and retry presets.
// -----------------------------------------------------------------------------

package conn_manager

import (
	"fmt"
	"io"
	"net"
	"sync/atomic"
	"testing"
	"time"

	distributed_config "github.com/Bastien-Antigravity/distributed-config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
)

func TestConnectNonBlocking(t *testing.T) {
	nm := NewNetworkManagerWithPolicy(5, 100, 1000, 500, 2.0, 0.0)

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

	_ = mc.Close()
}

func TestOnErrorUnifiedHook(t *testing.T) {
	errorCount := 0
	lastAttempt := 0

	nm := NewNetworkManagerWithPolicy(2, 10, 100, 50, 1.0, 0.0)
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

func TestNetworkManager_ConnectCapability_Resolution(t *testing.T) {
	dConf := distributed_config.New("test")
	dConf.Capabilities = map[string]interface{}{
		"log-server": map[string]interface{}{
			"ip":   "127.0.0.1",
			"port": "7070",
		},
	}
	ac := &config.AppConfig{
		Profile: "test",
		Config:  dConf,
	}

	nm := NewNetworkManagerWithConfig(ac)
	nm.MaxRetries = 1

	mc, err := nm.ConnectCapability("log-server", ModeNonBlocking)
	if err != nil {
		t.Fatalf("ConnectCapability failed: %v", err)
	}
	if mc == nil {
		t.Fatal("Expected non-nil ManagedConnection")
	}

	ip, port := mc.GetEndpoint()
	if ip != "127.0.0.1" || port != "7070" {
		t.Errorf("Expected 127.0.0.1:7070, got %s:%s", ip, port)
	}
}

func TestNetworkManager_ConnectCapability_LiveConfigRefresh(t *testing.T) {
	dConf := distributed_config.New("test")
	dConf.Capabilities = map[string]interface{}{
		"log-server": map[string]interface{}{
			"ip":   "127.0.0.1",
			"port": "5000",
		},
	}
	ac := &config.AppConfig{
		Profile: "test",
		Config:  dConf,
	}

	nm := NewNetworkManagerWithConfig(ac)
	nm.MaxRetries = 1
	nm.BaseDelay = 5 * time.Millisecond

	mc, err := nm.ConnectCapability("log-server", ModeNonBlocking)
	if err != nil {
		t.Fatalf("ConnectCapability failed: %v", err)
	}

	// Update capability in LiveConfig simulating config-server broadcast
	dConf.Set(map[string]map[string]string{
		"log-server": {
			"ip":   "10.0.0.99",
			"port": "9999",
		},
	})

	// Next reconnect attempt immediately picks up the updated address from AppConfig
	_ = mc.reconnect()

	ip, port := mc.GetEndpoint()
	if ip != "10.0.0.99" || port != "9999" {
		t.Errorf("Expected endpoint updated to 10.0.0.99:9999 via AppConfig, got %s:%s", ip, port)
	}
}

func TestNetworkManager_UnifiedConstructor_And_LockFreeEndpoint(t *testing.T) {
	dConf := distributed_config.New("test")
	dConf.Capabilities = map[string]interface{}{
		"log-server": map[string]interface{}{
			"ip":   "127.0.0.1",
			"port": "7070",
		},
	}
	ac := &config.AppConfig{
		Profile: "test",
		Config:  dConf,
	}

	// 1. Unified constructor taking both ac and logger pointers in one function
	nm := NewNetworkManager(ac, nil)
	if nm.AppConfig != ac {
		t.Fatal("Expected AppConfig to be bound")
	}
	if nm.Logger == nil {
		t.Fatal("Expected non-nil logger")
	}

	// 2. Direct lock-free Endpoint creation
	ep := NewEndpoint("127.0.0.1", "7070", "1.2.3.4", "test")
	if ep.Address != "127.0.0.1:7070" {
		t.Fatalf("Expected precalculated address 127.0.0.1:7070, got %s", ep.Address)
	}

	mc := NewManagedConnection(nm, ep)
	loadedEP := mc.Endpoint()
	if loadedEP != ep {
		t.Fatal("Expected atomic pointer load to return exact immutable Endpoint pointer")
	}
	if loadedEP.PublicIP != "1.2.3.4" {
		t.Fatalf("Expected PublicIP 1.2.3.4, got %s", loadedEP.PublicIP)
	}

	// 3. Lock-free endpoint update
	mc.UpdateEndpoint("10.0.0.50", "8080")
	updatedEP := mc.Endpoint()
	if updatedEP.Address != "10.0.0.50:8080" {
		t.Fatalf("Expected updated address 10.0.0.50:8080, got %s", updatedEP.Address)
	}
	if updatedEP.PublicIP != "1.2.3.4" {
		t.Fatalf("Expected PublicIP preserved across update, got %s", updatedEP.PublicIP)
	}
}

func TestRealWorld_DynamicFailover_And_3TryReload(t *testing.T) {
	// 1. Setup in-memory net.Pipe pairs for Server 1 and Server 2
	s1Client, s1Server := net.Pipe()
	s1Received := make(chan string, 1)
	go func() {
		buf := make([]byte, 1024)
		n, _ := s1Server.Read(buf)
		if n > 0 {
			s1Received <- string(buf[:n])
		}
	}()

	s2Client, s2Server := net.Pipe()
	s2Received := make(chan string, 1)
	go func() {
		buf := make([]byte, 1024)
		n, _ := s2Server.Read(buf)
		if n > 0 {
			s2Received <- string(buf[:n])
		}
	}()

	server1Port := "9001"
	server2Port := "9002"

	// 2. Configure AppConfig pointing to Server 1 (port 9001)
	dConf := distributed_config.New("test")
	dConf.Capabilities = map[string]interface{}{
		"trade-engine": map[string]interface{}{
			"ip":      "127.0.0.1",
			"port":    server1Port,
			"profile": "tcp",
		},
	}
	ac := &config.AppConfig{
		Profile: "test",
		Config:  dConf,
	}

	// 3. Initialize NetworkManager with fast retry settings and custom Dialer simulating socket dispatch
	nm := NewNetworkManager(ac, nil)
	nm.MaxRetries = 10
	nm.BaseDelay = 5 * time.Millisecond
	nm.MaxDelay = 20 * time.Millisecond

	var server1Alive atomic.Bool
	server1Alive.Store(true)

	nm.Dialer = func(ep *Endpoint) (io.WriteCloser, error) {
		if ep.Port == server1Port {
			if !server1Alive.Load() {
				return nil, fmt.Errorf("connection refused: server 1 is dead")
			}
			return s1Client, nil
		}
		if ep.Port == server2Port {
			return s2Client, nil
		}
		return nil, fmt.Errorf("unknown port: %s", ep.Port)
	}

	// 4. Connect capability in NonBlocking mode
	mc, err := nm.ConnectCapability("trade-engine", ModeNonBlocking)
	if err != nil {
		t.Fatalf("ConnectCapability failed: %v", err)
	}
	defer func() { _ = mc.Close() }()

	// Wait for connection to be active
	deadline := time.Now().Add(1 * time.Second)
	for time.Now().Before(deadline) {
		if mc.currentConn.Load() != nil {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	if mc.currentConn.Load() == nil {
		t.Fatal("ManagedConnection failed to connect to server 1")
	}

	// 5. Send payload 1 to Server 1
	if _, err := mc.Write([]byte("order-1")); err != nil {
		t.Fatalf("Write to server 1 failed: %v", err)
	}

	select {
	case msg := <-s1Received:
		if msg != "order-1" {
			t.Fatalf("Expected 'order-1', got '%s'", msg)
		}
	case <-time.After(1 * time.Second):
		t.Fatal("Server 1 timed out waiting for payload")
	}

	// 6. Kill Server 1 (simulating crash)
	server1Alive.Store(false)
	_ = s1Server.Close()
	_ = s1Client.Close()
	time.Sleep(10 * time.Millisecond)

	// 7. Update AppConfig capability to point to Server 2 (simulating config-server dynamic capability update / self-registration)
	dConf.Capabilities["trade-engine"] = map[string]interface{}{
		"ip":      "127.0.0.1",
		"port":    server2Port,
		"profile": "tcp",
	}

	// 8. Write payload 2 to the same ManagedConnection.
	// Since Server 1 is dead, the write fails and triggers hot-path recovery:
	// - Clears dead socket
	// - Starts reconnection loop
	// - Attempt 1 fails (server 1 dead)
	// - Attempt 2 fails (server 1 dead)
	// - Attempt 3 triggers reload from AppConfig!
	// - AppConfig resolves trade-engine at port 9002!
	// - ManagedConnection updates Endpoint atomically to 127.0.0.1:9002
	// - Dials Server 2, establishes connection, and retries the pending write!
	if _, err := mc.Write([]byte("order-2")); err != nil {
		t.Fatalf("Write to server 2 via dynamic 3-try reload failed: %v", err)
	}

	select {
	case msg := <-s2Received:
		if msg != "order-2" {
			t.Fatalf("Expected 'order-2', got '%s'", msg)
		}
	case <-time.After(1 * time.Second):
		t.Fatal("Server 2 timed out waiting for payload after dynamic failover")
	}

	// 9. Verify Endpoint was updated to Server 2
	curIP, curPort := mc.GetEndpoint()
	if curPort != server2Port {
		t.Fatalf("Expected endpoint updated to port %s, got %s:%s", server2Port, curIP, curPort)
	}
}
