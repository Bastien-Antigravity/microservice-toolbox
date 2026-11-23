// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Client facade connecting Go services to the central tele-remote Telegram bot via gRPC.
//
// DATA FLOW:
// Service State -> TeleClient -> gRPC Stream -> TeleRemote Server -> Telegram Bot
//
// KEY PARAMETERS:
// - serviceName: Identifier displayed in Telegram menu.
// - addr: tele-remote server address.
// -----------------------------------------------------------------------------

package teleremote

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/teleremote/grpc_client"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/wiretap"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	toolbox_network "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/network"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
)

// -----------------------------------------------------------------------------
// Metadata Models (Internal for JSON parity)
// -----------------------------------------------------------------------------

type btnDef struct {
	Label       string   `json:"label"`
	Order       int      `json:"order,omitempty"`
	CmdType     int32    `json:"cmd_type,omitempty"`
	Payload     string   `json:"payload,omitempty"`
	InputPrompt string   `json:"input_prompt,omitempty"`
	Menu        []rowDef `json:"menu,omitempty"`
}

type rowDef struct {
	Order   int      `json:"order,omitempty"`
	Buttons []btnDef `json:"buttons"`
}

type menuEnvelope struct {
	Priority int      `json:"priority"`
	Rows     []rowDef `json:"rows"`
}

// -----------------------------------------------------------------------------
// Public Fluent API
// -----------------------------------------------------------------------------

// Action defines a single interactive element in the Telegram UI
type Action struct {
	Label       string
	Order       int
	SubMenu     []Action
	InputPrompt string                   // If set, bot asks user for text input
	Callback    func(input string) error // Handler receives optional user text
}

// -----------------------------------------------------------------------------
// TeleClient Implementation
// -----------------------------------------------------------------------------

// TeleClient maintains a resilient gRPC connection to tele-remote
type TeleClient struct {
	componentName string
	targetIP      string
	targetPort    int
	logger        logger.Logger

	mu         sync.RWMutex
	sendMu     sync.Mutex
	conn       *grpc.ClientConn
	stream     grpc_client.TeleRemoteService_ConnectClient
	cancelFunc context.CancelFunc

	// Automatic UI State
	priority int
	actions  []Action
	handlers map[string]func(string) error // label -> callback
	cmdChan  chan *grpc_client.BotCommand
	closed   bool

	// Optional Security & Transport Policy
	authToken  string
	tlsEnabled bool
	tlsMode    string
	tlsConfig  *tls.Config
	localTLS   toolbox_config.LocalTLSConfig
}

type teleRemoteCapability struct {
	TLSEnabled interface{} `json:"tls_enabled"`
	TLSMode    string      `json:"tls_mode"`
	AuthToken  string      `json:"auth_token"`
}

// NewTeleClient initializes a new Tele-Remote client
func NewTeleClient(componentName, targetIP string, targetPort int, l logger.Logger) *TeleClient {
	return &TeleClient{
		componentName: componentName,
		targetIP:      targetIP,
		targetPort:    targetPort,
		logger:        logger.EnsureSafeLogger(l),
		cmdChan:       make(chan *grpc_client.BotCommand, 100),
		handlers:      make(map[string]func(string) error),
	}
}

// SetPriority configures the OpenMFE menu priority for this component
func (tc *TeleClient) SetPriority(priority int) *TeleClient {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.priority = priority
	return tc
}

// SetAuthToken configures the shared secret sent in outgoing x-tele-auth gRPC metadata
func (tc *TeleClient) SetAuthToken(token string) *TeleClient {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.authToken = strings.TrimSpace(token)
	return tc
}

// SetTLSConfig configures an explicit TLS configuration for the gRPC connection
func (tc *TeleClient) SetTLSConfig(cfg *tls.Config) *TeleClient {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.tlsConfig = cfg
	return tc
}

// SetLocalTLS configures service-private X.509 TLS/mTLS file paths from the local: section
func (tc *TeleClient) SetLocalTLS(cfg toolbox_config.LocalTLSConfig) *TeleClient {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.localTLS = toolbox_config.LocalTLSConfig{
		CertFile:     strings.TrimSpace(cfg.CertFile),
		KeyFile:      strings.TrimSpace(cfg.KeyFile),
		CAFile:       strings.TrimSpace(cfg.CAFile),
		VerifyClient: cfg.VerifyClient,
	}
	return tc
}

// SetTLSPolicy configures local/remote-aware TLS enforcement
func (tc *TeleClient) SetTLSPolicy(enabled bool, mode string) *TeleClient {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.tlsEnabled = enabled
	tc.tlsMode = toolbox_network.NormalizeTLSMode(mode)
	return tc
}

// ConfigureFromAppConfig loads local X.509 credentials, fleet tele_remote TLS/auth policy,
// and registers a live-configuration callback to refresh them dynamically at runtime.
func (tc *TeleClient) ConfigureFromAppConfig(ac *toolbox_config.AppConfig, serviceKey string) error {
	if ac == nil || ac.Config == nil {
		return fmt.Errorf("TeleClient.ConfigureFromAppConfig requires non-nil AppConfig")
	}

	if err := tc.applyAppConfigPolicy(ac, serviceKey); err != nil {
		return err
	}

	ac.OnLiveConfUpdate(func(_ map[string]interface{}) {
		if err := tc.applyAppConfigPolicy(ac, serviceKey); err != nil {
			tc.logger.Warning("TeleClient live config refresh failed: %v", err)
		}
	})

	return nil
}

func (tc *TeleClient) applyAppConfigPolicy(ac *toolbox_config.AppConfig, serviceKey string) error {
	var trCap teleRemoteCapability
	if err := ac.Config.GetCapability("tele_remote", &trCap); err != nil {
		return err
	}

	tlsEnabled, err := parseCapabilityBool(trCap.TLSEnabled)
	if err != nil {
		return fmt.Errorf("invalid tele_remote.tls_enabled: %w", err)
	}

	authToken := strings.TrimSpace(trCap.AuthToken)
	if authToken != "" {
		decrypted, decErr := ac.DecryptSecret(authToken)
		if decErr != nil {
			return fmt.Errorf("failed to decrypt tele_remote.auth_token: %w", decErr)
		}
		authToken = decrypted
	}

	tc.SetLocalTLS(ac.GetLocalTLSConfig(serviceKey))
	tc.SetTLSPolicy(tlsEnabled, trCap.TLSMode)
	tc.SetAuthToken(authToken)
	return nil
}

func parseCapabilityBool(raw interface{}) (bool, error) {
	if raw == nil {
		return false, nil
	}
	switch v := raw.(type) {
	case bool:
		return v, nil
	case string:
		trimmed := strings.ToLower(strings.TrimSpace(v))
		switch trimmed {
		case "", "false":
			return false, nil
		case "true":
			return true, nil
		default:
			return false, fmt.Errorf("expected boolean or \"true\"/\"false\", got %q", v)
		}
	default:
		return false, fmt.Errorf("expected boolean or string, got %T", raw)
	}
}

// AddAction registers a new action or sub-menu tree
func (tc *TeleClient) AddAction(a Action) {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.actions = append(tc.actions, a)
	tc.registerHandlersRecursive(a)
}

// UpdateActions replaces all current actions and handlers
func (tc *TeleClient) UpdateActions(actions []Action) {
	tc.mu.Lock()
	defer tc.mu.Unlock()
	tc.actions = actions
	tc.handlers = make(map[string]func(string) error)
	for _, a := range actions {
		tc.registerHandlersRecursive(a)
	}
}

func (tc *TeleClient) registerHandlersRecursive(a Action) {
	if a.Callback != nil {
		tc.handlers[a.Label] = a.Callback
	}
	for _, sub := range a.SubMenu {
		tc.registerHandlersRecursive(sub)
	}
}

// Start initiates the connection and registration process
func (tc *TeleClient) Start() {
	go tc.connectionManager()
	go tc.commandDispatcher()
}

// GenerateMenuJSON returns the structured JSON representation of the action tree
func (tc *TeleClient) GenerateMenuJSON() string {
	tc.mu.RLock()
	defer tc.mu.RUnlock()

	rows := make([]rowDef, 0, len(tc.actions))
	for _, a := range tc.actions {
		btn := tc.convertActionToBtn(a)
		row := rowDef{Buttons: []btnDef{btn}}
		if a.Order > 0 {
			row.Order = a.Order
		}
		rows = append(rows, row)
	}

	if tc.priority > 0 {
		data, _ := json.Marshal(menuEnvelope{
			Priority: tc.priority,
			Rows:     rows,
		})
		return string(data)
	}

	data, _ := json.Marshal(rows)
	return string(data)
}

func (tc *TeleClient) convertActionToBtn(a Action) btnDef {
	btn := btnDef{
		Label:       a.Label,
		InputPrompt: a.InputPrompt,
	}
	if a.Order > 0 {
		btn.Order = a.Order
	}

	if len(a.SubMenu) > 0 || a.Callback == nil {
		// Recursive Menu Generation - one button per row
		subRows := make([]rowDef, 0, len(a.SubMenu))
		for _, subA := range a.SubMenu {
			subBtn := tc.convertActionToBtn(subA)
			subRow := rowDef{Buttons: []btnDef{subBtn}}
			if subA.Order > 0 {
				subRow.Order = subA.Order
			}
			subRows = append(subRows, subRow)
		}
		btn.Menu = subRows
	} else {
		// Command Leaf
		btn.CmdType = 99
		btn.Payload = a.Label // Unique routing key
	}

	return btn
}

// PushMenuUpdate manually triggers the background transmission of the current UI state.
// This is typically called by microservices after updating their Actions or internal state.
func (tc *TeleClient) PushMenuUpdate() {
	tc.mu.RLock()
	stream := tc.stream
	tc.mu.RUnlock()

	if stream != nil {
		go tc.sendRegistration(stream)
	}
}

// SendTelemetry streams an arbitrary text message to the Telegram admin chat
func (tc *TeleClient) SendTelemetry(msg string) error {
	tc.mu.RLock()
	stream := tc.stream
	tc.mu.RUnlock()

	if stream == nil {
		return fmt.Errorf("not connected to tele-remote")
	}

	payload := &grpc_client.ComponentMessage{
		ComponentName: tc.componentName,
		Payload: &grpc_client.ComponentMessage_Telemetry{
			Telemetry: msg,
		},
	}

	tc.sendMu.Lock()
	defer tc.sendMu.Unlock()
	err := stream.Send(payload)
	if wiretap.IsEnabled() {
		wiretap.RecordEvent(
			tc.componentName,
			"tele_remote",
			"GRPC",
			"HTTP/2 Protobuf (Stream)",
			"teleremote:telemetry",
			"telemetry",
			"outbound",
			msg,
			len(msg),
			0,
			err != nil,
			false,
		)
	}
	return err
}

func (tc *TeleClient) connectionManager() {
	addr := fmt.Sprintf("%s:%d", tc.targetIP, tc.targetPort)
	if wiretap.GetLocalService() == "unknown_service" && tc.componentName != "" {
		wiretap.SetLocalService(tc.componentName)
	}

	for {
		tc.mu.RLock()
		if tc.closed {
			tc.mu.RUnlock()
			return
		}
		explicitTLS := tc.tlsConfig
		tlsEnabled := tc.tlsEnabled
		tlsMode := tc.tlsMode
		localTLS := tc.localTLS
		targetIP := tc.targetIP
		authToken := tc.authToken
		tc.mu.RUnlock()

		var transportCreds credentials.TransportCredentials
		if explicitTLS != nil {
			transportCreds = credentials.NewTLS(explicitTLS)
		} else {
			var tlsErr error
			transportCreds, tlsErr = toolbox_network.DialTransportCredentials(localTLS, targetIP, tlsEnabled, tlsMode)
			if tlsErr != nil {
				tc.logger.Warning("TeleClient failed to resolve TLS credentials for %s: %v", addr, tlsErr)
				time.Sleep(5 * time.Second)
				continue
			}
		}

		tc.logger.Info("TeleClient connecting to %s...", addr)

		dialOpts := append(
			[]grpc.DialOption{grpc.WithTransportCredentials(transportCreds)},
			wiretap.ClientDialOptions("tele_remote")...,
		)
		conn, err := grpc.Dial(addr, dialOpts...)
		if err != nil {
			tc.logger.Warning("TeleClient connection failed: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		client := grpc_client.NewTeleRemoteServiceClient(conn)
		ctx, cancel := context.WithCancel(context.Background())
		if authToken != "" {
			ctx = metadata.NewOutgoingContext(ctx, metadata.Pairs("x-tele-auth", authToken))
		}

		stream, err := client.Connect(ctx)
		if err != nil {
			tc.logger.Warning("TeleClient stream creation failed: %v", err)
			conn.Close()
			cancel()
			time.Sleep(5 * time.Second)
			continue
		}

		tc.mu.Lock()
		tc.conn = conn
		tc.stream = stream
		tc.cancelFunc = cancel
		tc.mu.Unlock()

		// 1. Initial Registration
		tc.sendRegistration(stream)

		tc.logger.Info("TeleClient successfully registered with tele-remote")

		// 2. Receive loop
		for {
			cmd, err := stream.Recv()
			if err != nil {
				tc.logger.Warning("TeleClient disconnected from tele-remote: %v", err)
				break
			}

			if wiretap.IsEnabled() && cmd != nil {
				wiretap.RecordEvent(
					"tele_remote",
					tc.componentName,
					"GRPC",
					"HTTP/2 Protobuf (Stream)",
					"teleremote:command",
					"command",
					"inbound",
					cmd.CustomPayload,
					len(cmd.CustomPayload)+len(cmd.Input),
					0,
					false,
					false,
				)
			}

			if cmd.CommandType == grpc_client.BotCommand_REFRESH_MENU {
				tc.logger.Info("TeleClient received REFRESH_MENU request")
				tc.sendRegistration(stream)
				continue
			}

			tc.mu.RLock()
			isClosed := tc.closed
			tc.mu.RUnlock()

			if isClosed {
				break
			}

			select {
			case tc.cmdChan <- cmd:
			default:
				tc.logger.Warning("TeleClient command channel full, dropping command")
			}
		}

		tc.disconnect()
		time.Sleep(3 * time.Second)
	}
}

func (tc *TeleClient) sendRegistration(stream grpc_client.TeleRemoteService_ConnectClient) {
	menu := tc.GenerateMenuJSON()
	regMsg := &grpc_client.ComponentMessage{
		ComponentName: tc.componentName,
		Host:          "127.0.0.1",
		Port:          int32(tc.targetPort),
		Payload: &grpc_client.ComponentMessage_Registration{
			Registration: &grpc_client.Registration{
				MenuJson: menu,
			},
		},
	}

	tc.sendMu.Lock()
	defer tc.sendMu.Unlock()
	err := stream.Send(regMsg)
	if wiretap.IsEnabled() {
		wiretap.RecordEvent(
			tc.componentName,
			"tele_remote",
			"GRPC",
			"HTTP/2 Protobuf (Stream)",
			"teleremote:registration",
			"registration",
			"outbound",
			"menu_sync",
			len(menu),
			0,
			err != nil,
			false,
		)
	}
	if err != nil {
		tc.logger.Error("TeleClient failed to send registration: %v", err)
	}
}

func (tc *TeleClient) commandDispatcher() {
	for cmd := range tc.cmdChan {
		tc.mu.RLock()
		handler, ok := tc.handlers[cmd.CustomPayload]
		tc.mu.RUnlock()

		if ok && handler != nil {
			tc.logger.Info("Executing automatic Tele-Remote command: %s (Input: %s)", cmd.CustomPayload, cmd.Input)
			go func(c *grpc_client.BotCommand) {
				if err := handler(c.Input); err != nil {
					tc.logger.Error("Tele-Remote command handler failed: %v", err)
				}
			}(cmd)
		} else {
			tc.logger.Warning("No handler registered for command payload: %s", cmd.CustomPayload)
		}
	}
}

func (tc *TeleClient) disconnect() {
	tc.mu.Lock()
	defer tc.mu.Unlock()

	if tc.cancelFunc != nil {
		tc.cancelFunc()
		tc.cancelFunc = nil
	}
	if tc.conn != nil {
		tc.conn.Close()
		tc.conn = nil
	}
	tc.stream = nil
}

// Close gracefully stops the client
func (tc *TeleClient) Close() {
	tc.mu.Lock()
	if tc.closed {
		tc.mu.Unlock()
		return
	}
	tc.closed = true
	tc.mu.Unlock()

	tc.disconnect()
	close(tc.cmdChan)
}
