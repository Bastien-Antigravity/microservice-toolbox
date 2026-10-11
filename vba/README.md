# Microservice Toolbox - VBA Module

A COM-compatible wrapper for the Bastien-Antigravity ecosystem, enabling Excel and Access applications to participate in the microservice mesh with 1:1 parity for core configuration and security.

## Features
- **Object-Oriented API**: Familiar class-based interfaces (`AppConfig`, `NotificationClient`) for VBA developers.
- **Go Bridge Integration**: Bridges directly to the high-performance Go core (`libdistconf` and `libnotif`) for configuration resolution and direct multi-channel gRPC notifications.
- **Hierarchy of Truth**: Respects the same layered priority and local file overrides as Go/Python/Rust.
- **Environment Expansion**: Supports Windows-native syntax.
- **Direct gRPC Alerts (100% Parity)**: Dispatch direct alerts (`Send`, `SendAlert`, `SendWithAttachment`) from Excel/Access macros into `notif-server` (port 1027) with fail-fast zero-silent-fallback guarantees.

## Usage

### Configuration Loading
```vba
Dim ac As New AppConfig
ac.LoadConfig "standalone"

' Access network addresses (Docker Guard aware)
Debug.Print ac.GetListenAddr("market-observer")

' Access local settings from [profile].yaml
Debug.Print ac.GetLocal("database_path")

' Decrypt secrets on-demand via Go RSA engine
Debug.Print ac.DecryptSecret("ENC(...)")
```

### Direct Notification Dispatch
```vba
Dim client As NotificationClient
Set client = Toolbox.NewNotificationClientFromConfig(ac)

' 1-line general alert
client.Send "Risk model updated for portfolio Alpha", "telegram"

' Categorized alert with severity level
client.SendAlert "CRITICAL", "VaR breach threshold exceeded: -4.2%", "risk_team,telegram"

' Alert with attachment
client.SendWithAttachment "REPORT", "Daily PnL ledger attached", "ledger.xlsx", "reports"
```

## Setup
1.  **Import Files**: Import `AppConfig.cls`, `NotificationClient.cls`, `DistConf.bas`, and `Toolbox.bas` into your VBA project (Alt+F11 -> File -> Import).
2.  **Dependencies**: Ensure `libdistconf.dll` and `libnotif.dll` (64-bit on Windows, `.dylib` on macOS) are located in the same directory as the workbook or in a system PATH / `/usr/local/lib` directory.
3.  **References**: No external COM references required (uses dynamic DLL binding).

## Architecture
The VBA module implements **In-Memory Mirroring** (Full Sync). At startup, it fetches the entire fleet configuration from the Go bridge and parses it into a local `Scripting.Dictionary` for sub-millisecond lookups. For outgoing telemetry and alerts, it bridges across the standard C ABI into `libnotif`, enabling native gRPC transport without requiring heavyweight C++ runtimes in Office.
