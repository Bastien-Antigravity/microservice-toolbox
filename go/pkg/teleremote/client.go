package teleremote

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/teleremote/grpc_client"
	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// -----------------------------------------------------------------------------
// Metadata Models (Internal for JSON parity)
// -----------------------------------------------------------------------------

type btnDef struct {
	Label       string   `json:"label"`
	CmdType     int32    `json:"cmd_type,omitempty"`
	Payload     string   `json:"payload,omitempty"`
	InputPrompt string   `json:"input_prompt,omitempty"`
	Menu        []rowDef `json:"menu,omitempty"`
}

type rowDef struct {
	Buttons []btnDef `json:"buttons"`
}

// -----------------------------------------------------------------------------
// Public Fluent API
// -----------------------------------------------------------------------------

// Action defines a single interactive element in the Telegram UI
type Action struct {
	Label       string
	SubMenu     []Action
	InputPrompt string                 // If set, bot asks user for text input
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
	conn       *grpc.ClientConn
	stream     grpc_client.TeleRemoteService_ConnectClient
	cancelFunc context.CancelFunc

	// Automatic UI State
	actions  []Action
	handlers map[string]func(string) error // label -> callback
	cmdChan  chan *grpc_client.BotCommand
	closed   bool
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

	var rows []rowDef

	for _, a := range tc.actions {
		btn := tc.convertActionToBtn(a)
		rows = append(rows, rowDef{Buttons: []btnDef{btn}})
	}

	data, _ := json.Marshal(rows)
	return string(data)
}

func (tc *TeleClient) convertActionToBtn(a Action) btnDef {
	btn := btnDef{
		Label:       a.Label,
		InputPrompt: a.InputPrompt,
	}

	if len(a.SubMenu) > 0 || a.Callback == nil {
		// Recursive Menu Generation - one button per row
		subRows := []rowDef{}
		for _, subA := range a.SubMenu {
			subBtn := tc.convertActionToBtn(subA)
			subRows = append(subRows, rowDef{Buttons: []btnDef{subBtn}})
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

	return stream.Send(payload)
}

func (tc *TeleClient) connectionManager() {
	addr := fmt.Sprintf("%s:%d", tc.targetIP, tc.targetPort)

	for {
		tc.mu.RLock()
		if tc.closed {
			tc.mu.RUnlock()
			return
		}
		tc.mu.RUnlock()

		tc.logger.Info("TeleClient connecting to %s...", addr)
		
		conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
		if err != nil {
			tc.logger.Warning("TeleClient connection failed: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		client := grpc_client.NewTeleRemoteServiceClient(conn)
		ctx, cancel := context.WithCancel(context.Background())
		
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

	if err := stream.Send(regMsg); err != nil {
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
