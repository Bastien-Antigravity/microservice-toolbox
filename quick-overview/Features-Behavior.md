---
microservice: microservice-toolbox
type: features-behavior
status: active
language: polyglot
tags:
- '#service/microservice-toolbox'
- '#type/features-behavior'
- '#state/active'
- '#ai/ignore'
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

### 2. The CLI Docker Guard & Config-Only Bindings (Networking)
To prevent CLI overrides from breaking automated container orchestration while preserving explicit YAML configuration:
- **Override Suppression (CLI Docker Guard)**: CLI flags for networking (`--host`, `--port`, `--grpc_host`, `--grpc_port`) are **strictly ignored** when `DOCKER_ENV=true` is detected, preserving the container YAML DNS configuration.
- **Verbatim Config Binding (`connectivity.Resolver`)**: Resolvers preserve the configured `AppConfig` IP, hostname, and port **verbatim** (no automatic `0.0.0.0` or interface-IP rewriting) and fail fast on empty values.

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

### 6. Resilient Connection Manager (conn_manager)
The `conn_manager` provides polyglot connection resilience (Go, Python, Rust, C++) with automatic reconnection, backoff, and error reporting.

#### Unified NetworkManager & AppConfig Integration
- **Unified Constructor**: Initialized via `NewNetworkManager(appConfig, logger)` (Go), `new_network_manager(app_config, logger)` (Python), `NetworkManager::New(app_config, logger)` (C++), and `new_network_manager(app_config, logger)` (Rust).
- **Automated Capability Resolution**: `ConnectCapability(capabilityName, mode)` resolves downstream target coordinates from `AppConfig` and binds dynamic self-healing directly to the connection.

#### Lock-Free Atomic Endpoint Pointer Architecture
- **Immutable Precalculated `Endpoint`**: Target coordinates (`IP`, `Port`, `PublicIP`, `Profile`, and `Address`) are encapsulated into an immutable `Endpoint` pointer structure constructed once on the cold path.
- **Zero Hot-Path Overhead & Paranoia**: Eliminates all defensive nil-checks (`if mc.publicIP != nil`), string formatting (`fmt.Sprintf`), and string trims on hot paths.
- **Lock-Free Hot-Path Execution**: Active transmission loops (`Write()`, `send()`, coordinate reads) load endpoints and sockets via atomic pointer loads (`atomic.Pointer[Endpoint]` and `atomic.Pointer[io.WriteCloser]` in Go, `std::shared_ptr<const Endpoint>` in C++, GIL-atomic reference assignment in Python, `Arc<RwLock<Endpoint>>` in Rust) with **zero mutex locks** on active paths.

#### Direct `AppConfig` Resolution on Reconnect
- When an active connection drops or fails, `ManagedConnection` clears the severed socket via `CompareAndSwap` and initiates reconnection with exponential backoff and randomized jitter.
- **Direct Atomic LiveConfig Lookup**: On reconnect, `ManagedConnection` queries `AppConfig` (`GetListenAddr(capability)`), which reads directly from the lock-free `LiveConfig` atomic pointer kept up-to-date by `config-server` broadcasts.
- If the target service restarted on a new port or a replacement instance registered its new address, `ManagedConnection` atomically swaps its `Endpoint` pointer to the new address and seamlessly reconnects on the very first attempt without requiring microservice restarts.

#### Connection Modes
- **Blocking**: The connection manager blocks the initiating thread until a connection is established or `max_retries` is reached.
- **Non-Blocking**: The manager returns immediately and handles reconnection asynchronously in the background.

#### Retry Strategies & Polyglot Parity
- **Infinite Retries (`max_retries = -1`)**: Used for critical self-healing. Reconnection loops run indefinitely, blocking the connection/writing tasks until the dependency recovers. **This is a design requirement, not a bug.**
- **Finite Retries (`max_retries > 0`)**: Standard strategies terminate reconnection attempts after the limit is reached and return a `MaxRetriesReached` error.

#### Best Practices
1. **Asynchronous Handshake**: Use `NonBlocking` mode to prevent microservice startup from hanging when downstream dependencies are offline.
2. **Synchronous Write Alert**: Synchronous calls to `Write`/`Send` trigger immediate inline reconnection upon failure. To prevent business logic from blocking during outages, wrap writes in buffered queues or handle reconnection events.

## Quality & Alignment Observations

- **Strict Polyglot Rules**: The project closely enforces the **Mirroring Mandate** and **Behavioral Identity** across the Go reference implementation and its target languages.
- **UTC Time Sovereignty**: The terminal logger and core UI components correctly utilize UTC timestamps, fulfilling the fleet-wide alignment requirements.
- **Active Governance**: AI-Init.md, AI-Project-DNA.md, and AI-Session-State.md are correctly registered in the workspace, ensuring agents starting context are well-anchored.
