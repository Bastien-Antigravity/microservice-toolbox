# Microservice Toolbox - VBA Module

A COM-compatible wrapper for the Bastien-Antigravity ecosystem, enabling Excel and Access applications to participate in the microservice mesh with 1:1 parity for core configuration and security.

## Features
- **Object-Oriented API**: Familiar class-based interface (`AppConfig`) for VBA developers.
- **Go Bridge Integration**: Bridges directly to the high-performance Go core for RSA decryption and configuration resolution.
- **Hierarchy of Truth**: Respects the same layered priority and local file overrides as Go/Python/Rust.
- **Environment Expansion**: Supports Windows-native `` and `` syntax.

## Usage

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

## Setup
1.  **Import Files**: Import `AppConfig.cls`, `DistConf.bas`, and `Toolbox.bas` into your VBA project (Alt+F11 -> File -> Import).
2.  **Dependencies**: Ensure `libdistconf.dll` (64-bit) is located in the same directory as the workbook or in a system PATH directory.
3.  **References**: No external COM references required (uses dynamic DLL binding).

## Architecture
The VBA module implements **In-Memory Mirroring** (Full Sync). At startup, it fetches the entire fleet configuration from the Go bridge and parses it into a local `Scripting.Dictionary` for sub-millisecond lookups, eliminating the overhead of frequent COM-to-CGO calls.
