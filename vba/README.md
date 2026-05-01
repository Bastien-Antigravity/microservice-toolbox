# Microservice Toolbox - VBA Module

A COM-compatible wrapper for the Bastien-Antigravity ecosystem, enabling Excel and Access applications to participate in the microservice mesh.

## Features
- **Object-Oriented API**: Familiar class-based interface for VBA developers.
- **Dynamic Decryption**: Bridges to the Go core for `ENC(...)` secret handling.
- **Environment Expansion**: Supports `${VAR}` and `${VAR:default}` syntax on Windows.

## Usage

```vba
Dim ac As New AppConfig
ac.Init "standalone"

' Access network addresses
Debug.Print ac.GetListenAddr("my-service")

' Access local settings
Debug.Print ac.GetLocal("local_setting")

' Decrypt secrets
Debug.Print ac.DecryptSecret("ENC(...)")
```

## Setup
1.  Import `AppConfig.cls`, `DistConf.bas`, and `Toolbox.bas` into your VBA project.
2.  Ensure `libdistconf.dll` (Windows) is in the same directory as the workbook or in the system PATH.
