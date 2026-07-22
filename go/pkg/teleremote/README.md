# Tele-Remote Client (Go)

The `teleremote` package in the microservice-toolbox provides a robust, interface-driven way to project a Go microservice's capabilities into the centralized Telegram Bot UI.

## Features
- **Fluent API**: Define your UI tree and logic handlers in Go code.
- **Bi-directional gRPC**: Real-time telemetry pushing and command receiving.
- **Pull-on-Click Refresh**: UI automatically updates when users interact with it.
- **Input Prompts**: Easily ask the user for text input (e.g., "Enter price") and receive it in your callback.
- **Auto-Reconnect**: Transparent background connection management.

---

## Basic Usage

### 1. Initialize the Client
```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/teleremote"

tc := teleremote.NewTeleClient("My Service", "127.0.0.1", 50051, logger)
```

### 2. Add Simple Commands
```go
tc.AddAction(teleremote.Action{
    Label: "🚀 Start Engine",
    Callback: func(input string) error {
        return myEngine.Start()
    },
})
```

### 3. Add Sub-Menus and Input Prompts
```go
tc.AddAction(teleremote.Action{
    Label: "📂 Settings",
    SubMenu: []teleremote.Action{
        {
            Label: "✏️ Set Threshold",
            InputPrompt: "Please enter the new threshold value:",
            Callback: func(input string) error {
                return myEngine.SetThreshold(input)
            },
        },
    },
})
```

### 4. Start and Manage Lifecycle
```go
tc.Start()
defer tc.Close()
```

### 5. Send Telemetry
```go
tc.SendTelemetry("Alert: High latency detected on Binance feed")
```

---

## Architectural Specifications & BDD Protocol

This section details the communication and state expectations between any client microservice and the `tele-remote` bot. Follow these rules strictly when implementing new services or refactoring existing ones.

### 1. Registration Payload Format (JSON Schema)
The client registers its UI by sending a JSON-serialized array of rows to `tele-remote` during the gRPC connection handshake. The JSON structure is represented as follows:

```json
[
  {
    "buttons": [
      {
        "label": "Button Label",
        "cmd_type": 99,
        "payload": "Button Label",
        "input_prompt": "Optional Prompt Text",
        "menu": []
      }
    ]
  }
]
```

### 2. Layout Stacking Specification
- **Requirement:** Dynamic menu buttons must be stacked vertically (exactly one button per line/row in the Telegram Reply Keyboard).
- **Implementation:** To enforce vertical stacking, the client must place each button in its own row object (`rowDef` containing `{"buttons": [btnDef]}`) both at the top-level menu list and within nested submenus. 
- **Bot Behavior:** The `tele-remote` bot preserves the row structure sent by the client. It must never flatten multiple rows into one horizontal line.

### 3. Button Classification Scenarios (BDD Rules)

#### Scenario A: Submenu Navigation
- **Given:** An `Action` has a non-nil `SubMenu` slice (or represents a navigation container) AND its `Callback` handler is `nil`.
- **When:** Serialized by the client, it must generate a `"menu"` array containing the nested sub-rows.
- **Then:** The `tele-remote` bot parses this button as a navigation node, setting its `NextMenu` target. Clicking this button transitions the user into the submenu on the bot side without sending any command callbacks to the client.

#### Scenario B: Command Execution
- **Given:** An `Action` has a non-nil `Callback` handler.
- **When:** Serialized by the client, it must include `"cmd_type": 99` and `"payload"` (set to the unique label string of the action).
- **Then:** The `tele-remote` bot registers this button's unique callback ID (`dyn_X`) and associates it with the client connection. When clicked, the bot publishes a command containing the payload back to the client via the gRPC stream, which triggers the registered callback.

#### Scenario C: Text Input Interactive Prompt
- **Given:** An `Action` has a non-empty `InputPrompt` string.
- **When:** Serialized by the client, the button object must include the `"input_prompt"` field.
- **Then:** When clicked in Telegram, the bot intercepts the command, sends the prompt message to the user, and goes into input wait mode. When the user replies with text, the bot forwards the user's text as the `input` argument in the callback command sent to the client.

#### Scenario D: Handling Empty Sub-Menus
- **Given:** An `Action` is a navigation node (`Callback == nil`) but currently has 0 sub-menu items (e.g., browsing a section with no children).
- **When:** Serialized by the client, it must explicitly output `"menu": []` (an empty array) rather than omitting the key.
- **Then:** The `tele-remote` bot sees the `"menu"` field present, classifying it correctly as a submenu (rendering an empty page with a back button) rather than falling back to treating it as an action command leaf (which would throw warnings due to missing handlers).

---

## Component Synchronization Flow
```
+--------------+                   +-------------+
| Microservice |                   | Tele-Remote |
+--------------+                   +-------------+
       |                                  |
       |  gRPC Connection Handshake       |
       |--------------------------------->|
       |  Menu JSON Registration          |
       |  (Single button per row format)  |
       |                                  |
       |                                  |
       |  User presses Service Name       |
       |  in Bot Main Menu                |
       |  <-------------------------------|
       |  (Triggers REFRESH_MENU signal)  |
       |                                  |
       |  Re-builds Menu from active state|
       |  and sends updated Menu JSON     |
       |--------------------------------->|
       |                                  |
       |                                  |
       |  User clicks Action Button       |
       |  (or replies to input prompt)    |
       |  <-------------------------------|
       |  (Sends BotCommand with payload) |
       |                                  |
       |  Client runs Go Callback         |
       |  (triggers state update)         |
       |                                  |
```
