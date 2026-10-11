// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit and integration tests for NotificationClient facade in microservice-toolbox.
//
// DATA FLOW:
// Test -> NotificationClient -> Mock gRPC Server -> Assertion Verification
//
// KEY PARAMETERS:
// - mockNotifServer: Test gRPC server implementing NotifServiceServer.
// -----------------------------------------------------------------------------

package notification

import (
	"context"
	"net"
	"testing"
	"time"

	distributed_config "github.com/Bastien-Antigravity/distributed-config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/notification/grpc_client"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
)

// mockServer implements grpc_client.NotifServiceServer for unit testing
type mockServer struct {
	grpc_client.UnimplementedNotifServiceServer
	receivedReq *grpc_client.NotifRequest
	success     bool
}

func (m *mockServer) SendNotification(ctx context.Context, req *grpc_client.NotifRequest) (*grpc_client.NotifResponse, error) {
	m.receivedReq = req
	return &grpc_client.NotifResponse{Success: m.success}, nil
}

func startMockServer(t *testing.T, success bool) (*mockServer, string, func()) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)

	s := grpc.NewServer()
	mock := &mockServer{success: success}
	grpc_client.RegisterNotifServiceServer(s, mock)

	go func() {
		_ = s.Serve(lis)
	}()

	cleanup := func() {
		s.Stop()
		_ = lis.Close()
	}

	return mock, lis.Addr().String(), cleanup
}

// -----------------------------------------------------------------------------

func TestNotificationClient_SendSuccess(t *testing.T) {
	mock, addr, cleanup := startMockServer(t, true)
	defer cleanup()

	client := NewClientWithTarget(addr, nil)
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := client.Send(ctx, "Hello from L2 service", "telegram", "discord")
	require.NoError(t, err)

	require.NotNil(t, mock.receivedReq)
	assert.Equal(t, "Hello from L2 service", mock.receivedReq.Message)
	assert.Equal(t, []string{"telegram", "discord"}, mock.receivedReq.Tags)
	assert.Equal(t, "", mock.receivedReq.Level)
}

// -----------------------------------------------------------------------------

func TestNotificationClient_SendAlert(t *testing.T) {
	mock, addr, cleanup := startMockServer(t, true)
	defer cleanup()

	client := NewClientWithTarget(addr, nil)
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := client.SendAlert(ctx, "TRADE", "Filled order #1092: Bought 2.5 BTC", "trade_channel")
	require.NoError(t, err)

	require.NotNil(t, mock.receivedReq)
	assert.Equal(t, "Filled order #1092: Bought 2.5 BTC", mock.receivedReq.Message)
	assert.Equal(t, "TRADE", mock.receivedReq.Level)
	assert.Equal(t, []string{"trade_channel"}, mock.receivedReq.Tags)
}

// -----------------------------------------------------------------------------

func TestNotificationClient_SendWithAttachment(t *testing.T) {
	mock, addr, cleanup := startMockServer(t, true)
	defer cleanup()

	client := NewClientWithTarget(addr, nil)
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := client.SendWithAttachment(ctx, "REPORT", "Daily PnL Report", "/tmp/report.pdf", "finance")
	require.NoError(t, err)

	require.NotNil(t, mock.receivedReq)
	assert.Equal(t, "Daily PnL Report", mock.receivedReq.Message)
	assert.Equal(t, "REPORT", mock.receivedReq.Level)
	assert.Equal(t, "/tmp/report.pdf", mock.receivedReq.Attachment)
	assert.Equal(t, []string{"finance"}, mock.receivedReq.Tags)
}

// -----------------------------------------------------------------------------

func TestNotificationClient_ServerRejection(t *testing.T) {
	_, addr, cleanup := startMockServer(t, false)
	defer cleanup()

	client := NewClientWithTarget(addr, nil)
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := client.Send(ctx, "Test message")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "notification server rejected message")
}

// -----------------------------------------------------------------------------

func TestNotificationClient_ClosedClient(t *testing.T) {
	client := NewClientWithTarget("127.0.0.1:9999", nil)
	err := client.Close()
	require.NoError(t, err)

	err = client.Send(context.Background(), "Should fail")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "closed")
}

// -----------------------------------------------------------------------------

func TestNotificationClient_NilAppConfig(t *testing.T) {
	_, err := NewClient(nil, nil)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "appConfig cannot be nil")
}

// -----------------------------------------------------------------------------

func TestNotificationClient_AppConfigResolution(t *testing.T) {
	// Test resolution with custom capability port
	mock, addr, cleanup := startMockServer(t, true)
	defer cleanup()

	host, port, err := net.SplitHostPort(addr)
	require.NoError(t, err)

	distCfg := distributed_config.New("standalone")
	distCfg.Capabilities = map[string]interface{}{
		"notif_server": map[string]interface{}{
			"grpc_ip":   host,
			"grpc_port": port,
		},
	}
	appConfig := &config.AppConfig{
		Config: distCfg,
	}

	client, err := NewClient(appConfig, nil)
	require.NoError(t, err)
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err = client.Send(ctx, "Test config resolution")
	require.NoError(t, err)
	assert.Equal(t, "Test config resolution", mock.receivedReq.Message)
}

// -----------------------------------------------------------------------------

func TestNotificationClient_MissingCapabilityFailsFast(t *testing.T) {
	distCfg := distributed_config.New("standalone")
	distCfg.Capabilities = map[string]interface{}{}
	appConfig := &config.AppConfig{
		Config: distCfg,
	}

	client, err := NewClient(appConfig, nil)
	assert.Error(t, err)
	assert.Nil(t, client)
	assert.Contains(t, err.Error(), "failed to resolve notif_server gRPC address")
}
