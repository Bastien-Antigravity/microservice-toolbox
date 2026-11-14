# Architecture: Go Microservice Toolbox

The Go implementation serves as the **Reference Implementation** for the entire polyglot ecosystem. It contains the core logic for the "Hierarchy of Truth" and the Docker Guard resolution.

## 1. Hierarchy of Truth
Configuration is resolved in the following priority:
1.  **CLI Flags**: Highest priority (e.g., `--key path/to/private.pem`).
2.  **Environment Variables**: OS-level overrides (e.g., `BASTIEN_PRIVATE_KEY_PATH`).
3.  **Local YAML**: File-based settings (e.g., `standalone.yaml`).
4.  **Remote/Defaults**: Infrastructure-level settings.

## 2. Docker Guard & Config-Only Networking
A specialized networking guard that prevents CLI overrides from breaking automated container orchestration:
- **CLI Docker Guard (`config/args.go`)**: Inside containers (`/.dockerenv` or `DOCKER_ENV=true`), CLI network overrides (`--host`, `--port`, `--grpc_host`, `--grpc_port`) are strictly ignored so container YAML DNS routing is never overwritten.
- **Config-Only Bindings**: `connectivity.Resolver` and network servers preserve the IP, hostname, and port configured in `AppConfig` **verbatim** (never rewriting configured addresses to `0.0.0.0` or interface IPs) and fail fast on missing values.

## 3. Decryption Engine
Integrates directly with `distributed-config` to handle `ENC(...)` blocks. It uses process-local environment variables to discover the RSA keys, allowing for seamless CLI overrides via the `--key` flag.

## 4. Local Configuration (`Local`)
The `AppConfig` struct includes a `Local` map (parsed from the `local:` YAML section). This section is reserved for service-specific, non-synchronized settings.
- `UnmarshalLocal(target)`: Decodes this section into a user-provided struct.

## 5. Standardized Serialization (JSON vs. MsgPack vs. Cap'n Proto)
The Go toolbox provides interchangeable serialization providers via the `Serializer` interface:
- **JSON (`NewJSONSerializer`)**: Human-readable standard.
- **MsgPack (`NewBinSerializer`)**: High-performance, language-agnostic binary format. Use this for high-frequency microservice communication.
- **Cap'n Proto**: Ultra-low latency "Zero-Copy" format. Supported via schemas in `/schemas`. Currently requires using generated code directly as it bypasses the generic `interface{}`-based Marshaller for performance reasons.

**Ease of Switch**: Business logic remains decoupled from the format. Switching from JSON to MsgPack is a single line change in the service initialization:
```go
// From
serializer := serializers.NewJSONSerializer()
// To
serializer := serializers.NewBinSerializer()
```

## 6. Standardized Business Data
The Go implementation defines the canonical business data models in `pkg/business`. This package provides the standardized structure for the fleet:
- **MarketEvent**: A unified envelope for L1/L2 data (Trades, Quotes, OrderBooks).
- **OHLCV**: Canonical bar data for time-series analysis.
- **Signal**: Unified trading strategy signals (Buy/Sell/Exit).

All business services should use these models for inter-service communication to maintain structural integrity across the hierarchy.

## 7. Polyglot Parity & Development Rules
The `microservice-toolbox` is a polyglot foundation. To maintain ecosystem stability, the following rules apply to all contributors:

### 7.1 Mirroring Mandate
Whenever a new feature, model, or helper function is added to the Go (Reference) implementation, it **MUST** be ported to all other supported languages (Python, C++, Rust, VBA) within the same development cycle. No feature is considered "Done" until parity is achieved.

### 7.2 Semantic Consistency
Behavior must be identical across all implementations. If `UnmarshalLocal` in Go returns a specific error for a missing key, the Python and Rust implementations must mimic this behavior exactly.

### 7.3 Naming Conventions
To ensure a consistent developer experience while respecting language idioms, we follow these naming rules:
- **Go**: `PascalCase` for public methods/structs (e.g., `GetListenAddr`).
- **Python/Rust**: `snake_case` (e.g., `get_listen_addr`).
- **C++**: `camelCase` or `PascalCase` (following the project's C++ style).
- **Semantics**: The core word sequence must be identical across all languages. Do not use `fetch_ip` in Python if the Go equivalent is `GetListenAddr`.

### 7.4 Verification
Cross-language compatibility is verified via the `integration/` suite. Any change to the toolbox must pass the polyglot matrix tests to ensure that a value serialized in one language can be reliably deserialized in another.

## 8. Resilient Connection Manager (`conn_manager`)
The Go implementation serves as the reference architecture for network resilience, automated dynamic failover, and zero-lock hot-path connectivity:
- **Unified Constructor**: `NewNetworkManager(ac *config.AppConfig, l logger.Logger)` binds `AppConfig` and logger pointers directly.
- **Lock-Free Atomic Endpoint Architecture**: All destination parameters are encapsulated in an immutable, precalculated `Endpoint` struct (`IP`, `Port`, `PublicIP`, `Profile`, `Address`). `ManagedConnection` loads endpoints and socket writers via `atomic.Pointer[Endpoint]` and `atomic.Pointer[io.WriteCloser]`. The steady-state hot path (`Write()`) has **zero mutex locks**, zero defensive nil checks, and zero temporary string formatting.
- **Dynamic 3-Try Config Reload Contract**: On severed connections, reconnection loops use exponential backoff and randomized jitter. At attempt 3 (and every 3 attempts thereafter), `ManagedConnection` queries `AppConfig` (or calls `OnReloadConfig`). If a broken process restarted on a new port or an emergency fallback registered its address, the `Endpoint` pointer is atomically swapped to the new address and the pending write retries seamlessly.
- **Testability & Sandboxing**: `NetworkManager.Dialer` allows plugging mock or in-memory transports (`net.Pipe()`) to verify complete multi-service reconnect and failover scenarios in sandboxed environments without requiring raw OS socket permissions.
