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
	"sync"
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

type trackingWriteCloser struct {
	closed atomic.Bool
}

func (twc *trackingWriteCloser) Write(p []byte) (int, error) {
	if twc.closed.Load() {
		return 0, io.ErrClosedPipe
	}
	return len(p), nil
}

func (twc *trackingWriteCloser) Close() error {
	twc.closed.Store(true)
	return nil
}

func TestManagedConnection_ConcurrentClose_NoPanic(t *testing.T) {
	nm := NewNetworkManager(nil, nil)
	ep := NewEndpoint("127.0.0.1", "9090", "", "tcp")
	mc := NewManagedConnection(nm, ep)

	mockConn := &trackingWriteCloser{}
	var wc io.WriteCloser = mockConn
	mc.currentConn.Store(&wc)

	const goroutines = 100
	var wg sync.WaitGroup
	wg.Add(goroutines)
	start := make(chan struct{})

	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			<-start
			_ = mc.Close()
		}()
	}

	close(start)
	wg.Wait()

	if !mockConn.closed.Load() {
		t.Fatal("Expected underlying connection to be closed")
	}
	if mc.currentConn.Load() != nil {
		t.Fatal("Expected currentConn to be nil after Close()")
	}
}

func TestManagedConnection_CloseDuringDial_ClosesNewSocketAndLeavesCurrentConnNil(t *testing.T) {
	nm := NewNetworkManagerWithPolicy(3, 10, 50, 50, 1.0, 0.0)
	ep := NewEndpoint("127.0.0.1", "9091", "", "tcp")

	dialStarted := make(chan struct{})
	allowDialReturn := make(chan struct{})
	dialedConn := &trackingWriteCloser{}

	nm.Dialer = func(target *Endpoint) (io.WriteCloser, error) {
		close(dialStarted)
		<-allowDialReturn
		return dialedConn, nil
	}

	mc := NewManagedConnection(nm, ep)

	reconnectDone := make(chan error, 1)
	go func() {
		reconnectDone <- mc.reconnect()
	}()

	// Wait until Dialer is blocked inside EstablishConnection
	<-dialStarted

	// Call Close() while Dialer is blocked
	if err := mc.Close(); err != nil {
		t.Fatalf("Unexpected error on Close(): %v", err)
	}

	// Unblock Dialer so EstablishConnection returns (dialedConn, nil)
	close(allowDialReturn)

	err := <-reconnectDone
	if err == nil {
		t.Fatal("Expected reconnect() to return error when closed during dial")
	}
	if !dialedConn.closed.Load() {
		t.Fatal("Expected newly dialed connection to be immediately closed on shutdown race")
	}
	if mc.currentConn.Load() != nil {
		t.Fatal("Expected currentConn to remain nil after Close() during dial")
	}
}

func TestNetworkManager_WithPolicy_ClampingAndConnectEndpointFailure(t *testing.T) {
	nm := NewNetworkManagerWithPolicy(-5, -100, -50, -10, 0.2, 2.5)
	if nm.MaxRetries != -1 {
		t.Errorf("Expected MaxRetries clamped to -1, got %d", nm.MaxRetries)
	}
	if nm.BaseDelay != 0 {
		t.Errorf("Expected BaseDelay clamped to 0, got %v", nm.BaseDelay)
	}
	if nm.MaxDelay != 0 {
		t.Errorf("Expected MaxDelay clamped to 0, got %v", nm.MaxDelay)
	}
	if nm.ConnectTimeout != 0 {
		t.Errorf("Expected ConnectTimeout clamped to 0, got %v", nm.ConnectTimeout)
	}
	if nm.Backoff != 1.0 {
		t.Errorf("Expected Backoff clamped to 1.0, got %v", nm.Backoff)
	}
	if nm.Jitter != 1.0 {
		t.Errorf("Expected Jitter clamped to 1.0, got %v", nm.Jitter)
	}

	// Verify ModeBlocking in ConnectEndpoint logs warning and triggers OnError when MaxRetries == 0
	var onErrorCount atomic.Int32
	nm.WithPolicy(0, 10, 5, 10, 0.5, -0.5)
	if nm.MaxDelay != nm.BaseDelay {
		t.Errorf("Expected MaxDelay clamped to BaseDelay (%v), got %v", nm.BaseDelay, nm.MaxDelay)
	}
	if nm.Jitter != 0.0 {
		t.Errorf("Expected negative Jitter clamped to 0.0, got %v", nm.Jitter)
	}
	nm.OnError = func(attempt int, err error, source string, msg string) {
		onErrorCount.Add(1)
	}

	ep := NewEndpoint("127.0.0.1", "9999", "", "tcp")
	mc := nm.ConnectEndpoint(ep, ModeBlocking)
	if mc == nil {
		t.Fatal("Expected non-nil ManagedConnection from ConnectEndpoint")
	}
	if onErrorCount.Load() != 1 {
		t.Errorf("Expected OnError to be triggered once on ModeBlocking failure with MaxRetries=0, got %d", onErrorCount.Load())
	}
}

type partialFailWriteCloser struct {
	partialBytes int
	closed       atomic.Bool
}

func (pf *partialFailWriteCloser) Write(p []byte) (int, error) {
	return pf.partialBytes, io.ErrShortWrite
}

func (pf *partialFailWriteCloser) Close() error {
	pf.closed.Store(true)
	return nil
}

type recordingWriteCloser struct {
	writes [][]byte
	closed atomic.Bool
}

func (rw *recordingWriteCloser) Write(p []byte) (int, error) {
	cp := append([]byte(nil), p...)
	rw.writes = append(rw.writes, cp)
	return len(p), nil
}

func (rw *recordingWriteCloser) Close() error {
	rw.closed.Store(true)
	return nil
}

func TestManagedConnection_PartialWrite_DoesNotReplayCorruptedFrame(t *testing.T) {
	nm := NewNetworkManager(nil, nil)
	nm.MaxRetries = 3
	nm.BaseDelay = time.Millisecond
	nm.MaxDelay = 5 * time.Millisecond

	freshConn := &recordingWriteCloser{}
	nm.Dialer = func(ep *Endpoint) (io.WriteCloser, error) {
		return freshConn, nil
	}

	ep := NewEndpoint("127.0.0.1", "9020", "", "tcp")
	mc := NewManagedConnection(nm, ep)

	broken := &partialFailWriteCloser{partialBytes: 4}
	var wc io.WriteCloser = broken
	mc.currentConn.Store(&wc)

	n, err := mc.Write([]byte("frame-001"))
	if err == nil {
		t.Fatal("Expected error on partial write, got nil")
	}
	if n != 4 {
		t.Fatalf("Expected partial byte count 4 returned, got %d", n)
	}
	if !broken.closed.Load() {
		t.Fatal("Expected corrupted socket to be closed after partial write")
	}
	if len(freshConn.writes) != 0 {
		t.Fatalf("Partial write MUST NOT auto-replay buffer on fresh stream, got %d writes", len(freshConn.writes))
	}

	// Next independent frame reconnects cleanly onto freshConn
	n2, err2 := mc.Write([]byte("frame-002"))
	if err2 != nil || n2 != len("frame-002") {
		t.Fatalf("Expected subsequent frame to reconnect cleanly, got n=%d err=%v", n2, err2)
	}
	if len(freshConn.writes) != 1 || string(freshConn.writes[0]) != "frame-002" {
		t.Fatalf("Expected only 'frame-002' on fresh stream, got %q", freshConn.writes)
	}
}
