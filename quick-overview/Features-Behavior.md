---
tags:
- '#ai/ignore'
- '#domain/configuration'
- '#domain/security'
- '#zone/3-fleet'
---

# 🛠️ Features & Behavior

## Core Infrastructure Capabilities

### 1. Smart Configuration Loader & The "Hierarchy of Truth"
Configuration resolution adheres to a strict layered priority mechanism to guarantee developer control and operational consistency.

```mermaid
graph TD
    A[1. Command Line Overrides e.g. --key, --host, --port] -->|Highest Priority| B[2. Environment Variables e.g. BASTIEN_PRIVATE_KEY_PATH]
    B -->|Priority 2| C[3. Local File Override [profile].yaml]
    C -->|Priority 3| D[4. Config Server Baseline]
    D -->|Lowest Priority| E[Resolved Configuration Struct]
```

- **Local Overrides namespace (local:)**: Enables developers to declare sandbox-specific variables that are never synchronized or checked in to the remote configuration server.
- **Universal Override Policy**: The local file override acts as an authoritative, unconditional override across all profiles (including production and staging environments) to ensure absolute alignment.
- **UnmarshalLocal Mapping**: Maps raw local sections directly into native structures in Go, Python, and Rust.

### 2. The Docker Guard (Networking)
To prevent hardcoded networking from breaking automated container orchestration, the toolbox implements a strict Docker Guard:
- **Loopback Translation**: If a service requests a bind to `127.0.0.1` inside a container, the toolbox automatically resolves this to the container's primary network interface IP.
- **Override Suppression**: CLI flags for networking (`--host`, `--port`, etc.) are **strictly ignored** when `/.dockerenv` is detected. This ensures that only the orchestrated container network is used for inter-service communication.

### 3. Hardened RSA Secret Management (v0.0.1+)
To prevent secret exposure, secrets remain in-memory as `ENC(...)` values. Decryption is performed on-demand via the centralized Go engine.

> [!IMPORTANT]
> Non-Go implementations (Python, Rust, C++, VBA) do not implement RSA cryptography independently. Instead, they bridge to the Go reference implementation to maintain a single cryptographic boundary and enforce absolute security alignment.

- **FFI Memory Mirroring**: Uses highly optimized in-memory key-value mirroring to complete config and secret lookups in sub-millisecond ranges.
- **Error Transparency**: Since v0.0.1+, engine-level decryption and structural failures pass through raw errors to the caller via the `GetLastError()` API, eliminating diagnostic opacity.

### 4. Business Data Standards (v0.0.1+)
Centralized schema specifications in `/schemas/business` define low-latency binary structures using Cap'n Proto for microsecond-sensitive applications:

| Data Model | Schema File | Go Native Struct | Python Binding | Rust Binding | C++ | VBA |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **MarketEvent** | `market_event.capnp` | `pkg/business/models.go` | `microservice_toolbox/business` | `src/business/` | ✅ | ❌ |
| **OHLCV** | `ohlcv.capnp` | `pkg/business/models.go` | `microservice_toolbox/business` | `src/business/` | ✅ | ❌ |
| Signal | `signal.capnp` | `pkg/business/models.go` | `microservice_toolbox/business` | `src/business/` | ✅ | ❌ |

### 5. Standardized Serialization Providers (JSON vs. MsgPack vs. Cap'n Proto)
The toolbox provides a unified, language-agnostic serialization layer to support different performance profiles across the fleet.

- **JSON (`NewJSONSerializer`)**: The default human-readable format. Best for configuration, API responses, and low-frequency debugging.
- **MsgPack (`NewBinSerializer`)**: A binary, schema-less format that is **fully language and machine agnostic**. It is significantly smaller and faster to parse than JSON, making it the standard for internal high-frequency microservice communication.
- **Cap'n Proto**: The ultra-low latency "Zero-Copy" tier. 
  - **Ease of Switch**: Services can swap between JSON and MsgPack with a single line change in the factory method. 
  - **Cap'n Proto Status**: While schemas are standardized in `schemas/business/`, switching to Cap'n Proto requires using generated code rather than the generic `Serializer` interface due to its strict schema-driven, zero-copy architecture.

#### Cap'n Proto Implementation Example (Go)
For microsecond-sensitive paths (e.g., market data ingestion), bypass the generic `Serializer` and use the generated Cap'n Proto bindings:

```go
import (
    "capnproto.org/go/capnp/v3"
    "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/business"
    "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/schemas/market_event"
)

func SerializeMarketEvent(evt business.MarketEvent) ([]byte, error) {
    msg, seg, err := capnp.NewMessage(capnp.SingleSegment(nil))
    if err != nil {
        return nil, err
    }

    // Initialize root struct
    root, err := market_event.NewRootMarketEvent(seg)
    if err != nil {
        return nil, err
    }

    // Set fields (Zero-copy allocation)
    root.SetEventId(evt.EventID)
    root.SetSymbol(evt.Symbol)
    root.SetTimestamp(evt.Timestamp)
    
    // Convert to byte slice
    return msg.Marshal()
}
```

## Quality & Alignment Observations


- **Strict Polyglot Rules**: The project closely enforces the **Mirroring Mandate** and **Behavioral Identity** across the Go reference implementation and its target languages.
- **UTC Time Sovereignty**: The terminal logger and core UI components correctly utilize UTC timestamps, fulfilling the fleet-wide alignment requirements.
- **Active Governance**: AI-Init.md, AI-Project-DNA.md, and AI-Session-State.md are correctly registered in the workspace, ensuring agents starting context are well-anchored.
