// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-level client facade enabling L2 and L3 microservices to send direct,
// multi-channel notifications to notif-server via resilient gRPC.
//
// DATA FLOW:
// L2/L3 Domain Event -> NotificationClient.Send / SendAlert -> gRPC (Port 1027) -> notif-server
//
// KEY PARAMETERS:
// - appConfig: Shared ecosystem AppConfig resolving notif_server gRPC capability.
// - targetAddr: Target gRPC address (host:port) of notif-server.
// - logger: Unified ecosystem logger instance.
// -----------------------------------------------------------------------------

package notification

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/notification/grpc_client"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// DefaultTimeout is the default duration for unary RPC dispatches if the caller context has no deadline.
const DefaultTimeout = 5 * time.Second

// -----------------------------------------------------------------------------
// NotificationClient
// -----------------------------------------------------------------------------

// NotificationClient provides a resilient, thread-safe gRPC client for dispatching
// notifications directly from L2/L3 microservices to notif-server.
type NotificationClient struct {
	targetAddr string
	logger     logger.Logger
	timeout    time.Duration

	mu     sync.RWMutex
	conn   *grpc.ClientConn
	client grpc_client.NotifServiceClient
	closed bool
}

// -----------------------------------------------------------------------------

// NewClient initializes a NotificationClient by dynamically resolving the notif_server
// capability address from the provided ecosystem AppConfig.
// It fails fast if the notif_server capability or its gRPC address is unresolvable.
func NewClient(appConfig *config.AppConfig, l logger.Logger) (*NotificationClient, error) {
	safeLogger := logger.EnsureSafeLogger(l)

	if appConfig == nil {
		return nil, fmt.Errorf("appConfig cannot be nil")
	}

	addr, err := appConfig.GetGRPCListenAddr("notif_server")
	if err != nil {
		return nil, fmt.Errorf("failed to resolve notif_server gRPC address: %w", err)
	}
	if addr == "" {
		return nil, fmt.Errorf("notif_server gRPC address is empty")
	}

	safeLogger.Info("NotificationClient configured with target address: %s", addr)

	return NewClientWithTarget(addr, safeLogger), nil
}

// -----------------------------------------------------------------------------

// NewClientWithTarget initializes a NotificationClient pointing to a specific target address.
// This is suitable for unit tests, custom service meshes, and explicit endpoint configurations.
func NewClientWithTarget(targetAddr string, l logger.Logger) *NotificationClient {
	return &NotificationClient{
		targetAddr: targetAddr,
		logger:     logger.EnsureSafeLogger(l),
		timeout:    DefaultTimeout,
	}
}

// -----------------------------------------------------------------------------

// SetTimeout configures the default dispatch timeout for RPC calls.
func (c *NotificationClient) SetTimeout(t time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.timeout = t
}

// -----------------------------------------------------------------------------

// Send is a 1-line helper dispatching an untyped or informational notification
// with optional destination tags (e.g. "telegram", "discord").
func (c *NotificationClient) Send(ctx context.Context, message string, tags ...string) error {
	return c.SendWithAttachment(ctx, "", message, "", tags...)
}

// -----------------------------------------------------------------------------

// SendAlert dispatches a categorized notification with a specific severity level
// (e.g., "TRADE", "CRITICAL", "WARNING", "REPORT", "INFO") and optional destination tags.
func (c *NotificationClient) SendAlert(ctx context.Context, level string, message string, tags ...string) error {
	return c.SendWithAttachment(ctx, level, message, "", tags...)
}

// -----------------------------------------------------------------------------

// SendWithAttachment dispatches a full notification payload including level, message,
// file/data attachment reference, and destination tags.
func (c *NotificationClient) SendWithAttachment(ctx context.Context, level, message, attachment string, tags ...string) error {
	client, err := c.getOrCreateClient()
	if err != nil {
		c.logger.Warning("Notification dispatch failed (cannot connect to %s): %v", c.targetAddr, err)
		return fmt.Errorf("notification client connection error: %w", err)
	}

	req := &grpc_client.NotifRequest{
		Message:    message,
		Tags:       tags,
		Attachment: attachment,
		Level:      level,
	}

	// Apply timeout guard if the caller context has no deadline
	reqCtx := ctx
	if reqCtx == nil {
		reqCtx = context.Background()
	}
	if _, hasDeadline := reqCtx.Deadline(); !hasDeadline {
		var cancel context.CancelFunc
		reqCtx, cancel = context.WithTimeout(reqCtx, c.timeout)
		defer cancel()
	}

	resp, err := client.SendNotification(reqCtx, req)
	if err != nil {
		c.logger.Warning("Notification dispatch to %s failed: %v", c.targetAddr, err)
		return fmt.Errorf("SendNotification RPC failed: %w", err)
	}

	if !resp.GetSuccess() {
		c.logger.Warning("Notification server rejected notification: success=false")
		return fmt.Errorf("notification server rejected message")
	}

	c.logger.Debug("Notification dispatched successfully to %s (level=%s, tags=%v)", c.targetAddr, level, tags)
	return nil
}

// -----------------------------------------------------------------------------

// Close terminates the active gRPC connection.
func (c *NotificationClient) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.closed = true
	if c.conn != nil {
		err := c.conn.Close()
		c.conn = nil
		c.client = nil
		return err
	}
	return nil
}

// -----------------------------------------------------------------------------

func (c *NotificationClient) getOrCreateClient() (grpc_client.NotifServiceClient, error) {
	c.mu.RLock()
	if c.closed {
		c.mu.RUnlock()
		return nil, fmt.Errorf("notification client is closed")
	}
	if c.client != nil {
		client := c.client
		c.mu.RUnlock()
		return client, nil
	}
	c.mu.RUnlock()

	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil, fmt.Errorf("notification client is closed")
	}
	if c.client != nil {
		return c.client, nil
	}

	conn, err := grpc.Dial(c.targetAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("failed to dial %s: %w", c.targetAddr, err)
	}

	c.conn = conn
	c.client = grpc_client.NewNotifServiceClient(conn)
	return c.client, nil
}
