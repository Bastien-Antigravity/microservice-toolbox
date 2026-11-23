# AGENTS.md: microservice-toolbox

## Service Mission & Architecture Role
`microservice-toolbox` is the canonical, cross-language developer framework and facade for the Bastien-Antigravity ecosystem. It standardizes service initialization (`BootstrapService`), configuration loading (wrapping `distributed-config`), logging setup (wrapping `universal-logger`), lifecycle management, and inter-service client connectivity across Go, Python, Rust, C++, and VBA.

- **Ecosystem Role**: Universal Facade and SDK.
- **Sub-packages (Go)**:
  - `go/pkg/bootstrap`: Single-call service initialization (`BootstrapService`, `BootstrapServiceSafe`)
  - `go/pkg/config`: Layered configuration management (`LoadConfig`, CLI overrides, port validation)
  - `go/pkg/conn_manager`: Resilient network connections with backoff and retry policies
  - `go/pkg/connectivity`: Config-driven address resolution (preserving configured `AppConfig` IPs/hosts/ports verbatim)
  - `go/pkg/lifecycle`: Graceful shutdown management (`Manager.Wait`), OS signal trapping (SIGINT/SIGTERM)
  - `go/pkg/network`: gRPC server builder consuming validated `AppConfig` addresses directly
  - `go/pkg/serializers`: Unified JSON and MsgPack binary serialization
  - `go/pkg/business`: Canonical market domain models (MarketEvent, OHLCV, Signal)
  - `go/pkg/teleremote`: Telegram bot client facade and menu tree builder
  - `go/pkg/logger`: Unified Logger abstraction compatible with universal-logger
  - `go/pkg/messaging`: Resilient NATS Core and JetStream connection manager
  - `go/pkg/notification`: Direct multi-channel notification client facade for L2/L3 services (gRPC port 1027 to notif-server)
  - `go/pkg/utils`: Terminal UI helpers, environment and formatting utilities
  - `go/pkg/version`: Internal `VERSION.txt`-only engine consumed directly by `appConfig.GetVersion()`
  - `go/pkg/schemas/logger`: Canonical Cap'n Proto `logger.capnp` wire schema SSoT and embedded `LoggerCapnpSchema` (symlinked at `schemas/platform/logger.capnp`)
  - `go/pkg/schemas/notifier`: Canonical Cap'n Proto `notifier.capnp` wire schema SSoT and embedded `NotifierCapnpSchema` (symlinked at `schemas/platform/notifier.capnp`)
  - `go/pkg/spec`: Authoritative declarative `ServiceSpec`, `BuildSpecFromConfig` auto-enrichment (`URL`, `Framing` ports, `version` via `appConfig.GetVersion()`, `ports`, `node`, `Health`, `Canvas`), `PublishWithLifecycle`, and Exchange Contract models/IDL extractors (`contracts.go`)
  - `go/pkg/wiretap`: Lock-free real-time transport telemetry aggregator (`SafeSocket`, gRPC, NATS, HTTP, MCP; mirrored in Python, Rust, and C++17)
- **Configuration Link**: `standalone.yaml -> ../docker-deployment/modes/local/config/native.yaml`

## Key Build & Test Commands
```bash
# Test Go package
go test -v ./go/...

# Test Python bindings
pytest python/

# Test Rust crate
cd rust && cargo test

# Test C and C++ spec/contracts suites
cd cpp && make test
```

## AI Development & Integration Guidelines
1. **API Parity Across Languages**: Maintain conceptual and naming symmetry between Go, Python, and Rust implementations.
2. **Never Bypass Engine Abstractions**: Go implementations wrap `distributed-config` and `universal-logger`. Do not introduce redundant config parsing.
3. **Cold-Path Fail-Fast Validation vs. Hot-Path Purity**: Validate required configuration, capabilities, and `VERSION.txt` once at boot/ingress, emitting explicit fatal errors on missing values instead of silent `"0.0.1"` / `"127.0.0.1"` / `"0.0.0.0"` fallbacks. Downstream hot paths MUST trust pre-validated `AppConfig` strings directly without redundant re-checks.
4. **Header Ritual**: All source files MUST contain the Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
5. **Section Dividers**: Use appropriate section dividers (`// ----...` for Go/Rust/C++, `# ----...` for Python).
6. **Two-Tier Logging & EnsureSafeLogger Standard**:
   - **Tier 1 (Libraries & Reusable SDKs)**: Reusable components and constructors across Go, Python, Rust, and C++ (`safe-socket`, `distributed-config`, `conn_manager`, `teleremote`, etc.) wrap injected loggers using `EnsureSafeLogger(l)` / `ensure_safe_logger(l)` to prevent nil pointer panics and eliminate repetitive `if logger != nil` branches.
   - **Tier 2 (Microservices)**: Production microservice entry points must initialize via `BootstrapService`, which guarantees a non-nil `Logger`. Calling `EnsureSafeLogger` or using no-op fallbacks in non-test microservice source code is strictly prohibited (`PRODUCTION_MOCK_POLLUTION`).
   - **Strict Mode Enforcement**: When `STRICT_LOGGER=true`, `EnsureSafeLogger` panics / raises `RuntimeError` immediately upon receiving `nil`, ensuring uninitialized dependencies fail-fast on boot rather than running dark.
7. **L1 Resilience, Connectivity & Self-Healing Contract**:
   - All inter-service connections must leverage `conn_manager`, `teleremote`, or `messaging` with infinite retries (`MaxRetries: -1` in `NewCriticalStrategy`) and exponential backoff with randomized jitter (`GetNextDelay`). Infinite retry is a design requirement for autonomous recovery.
   - **Unified NetworkManager & AppConfig Binding**: Initialize `NetworkManager` via `NewNetworkManager(appConfig, logger)` (Go), `new_network_manager(app_config, logger)` (Python), `NetworkManager::New(app_config, logger)` (C++), or `new_network_manager(app_config, logger)` (Rust). Call `ConnectCapability(cap, mode)` to bind capability resolution directly to `AppConfig`.
   - **Lock-Free Atomic Endpoint Pointer Architecture**: Destination coordinates (`IP`, `Port`, `PublicIP`, `Profile`, `Address`) are encapsulated into an immutable `Endpoint` pointer structure constructed once on the cold path. The hot path (`Write()`, `send()`, endpoint reads) is 100% lock-free via atomic pointer loads (`atomic.Pointer[Endpoint]` and `atomic.Pointer[io.WriteCloser]` with `CompareAndSwap` in Go, `std::atomic_load`/`std::atomic_store` on `shared_ptr<const Endpoint>` in C++, GIL-atomic reference assignment in Python, `Arc<RwLock<Arc<Endpoint>>>` in Rust) with zero defensive nil checks and zero local temporary variable unpacking.
   - **Direct `AppConfig` Resolution on Reconnect**: On severed sockets, `ManagedConnection` resolves the target capability directly from `AppConfig` (`LiveConfig` atomic pointer updated automatically by `config-server` broadcasts). If the target service restarted on a new port or a fallback registered its address, `ManagedConnection` atomically swaps its `Endpoint` pointer and reconnects immediately without requiring microservice restarts.
   - Non-blocking execution (`ModeNonBlocking`) is mandatory for peripheral discovery and registration hooks (such as OpenMFE) so microservice boot never hangs on offline downstream dependencies.
   - Address resolution must utilize `connectivity.Resolver` / `appConfig.GetListenAddr(...)`, which preserves the IP, hostname, and port configured in `AppConfig` verbatim (failing fast if empty) and never rewrites configured addresses to `0.0.0.0`. Inside Docker (`DOCKER_ENV=true`), `config` CLI Docker Guard ignores `--host`/`--port`/`--grpc_host`/`--grpc_port` flags so container YAML DNS config is preserved.
8. **Direct Notification Client Standard (`go/pkg/notification`, `python/microservice_toolbox/notification`, `rust/src/notification`, `cpp/include/.../NotificationClient.hpp`, `vba/NotificationClient.cls`)**:
   - L2 and L3 microservices (trading bots, schedulers, AI agents, Excel models) emitting direct business alerts (not system logs) must use:
     - Go: `notification.NewClient(appConfig, logger)`
     - Python: `NotificationClient.from_config(app_config, logger)`
     - Rust: `NotificationClient::from_config(&app_config, logger)`
     - C++: `NotificationClient::FromConfig(app_config, logger)`
     - VBA: `Toolbox.NewNotificationClientFromConfig(cfg)`
     to push to `notif-server` over gRPC (port 1027).
   - **Zero Silent Fallback**: Address resolution must strictly query `appConfig.GetGRPCListenAddr("notif_server")` / `get_grpc_listen_addr` and fail fast immediately if the capability is unresolvable or missing. Hardcoding fallback hosts/ports (e.g. `127.0.0.1:1027`) or redundant manual parsing loops is strictly prohibited.
   - **Polyglot Bridge Parity**: Python, Rust, C++, and VBA leverage the `libnotif` C ABI bridge (`Notif_Send`, `Notif_SendWithTimeout`) built by `notif-server`, guaranteeing 100% feature and protocol parity without heavyweight native gRPC compilation overhead. Go services use the native Go gRPC client in `go/pkg/notification` directly.
   - Distinguish strictly between `notification` (one-way alert) and `teleremote` (bi-directional bot command/menu streaming).
   - **Testing Ownership Standard**: In accordance with the 3-Tier Testing Pyramid, `microservice-toolbox` is the authoritative owner of all polyglot developer facade and client unit tests (`tests/` across Go, Python, Rust, C++). Low-level daemon repositories (like `notif-server`) compile the C ABI without maintaining duplicate client test suites, and `sandbox-testing` owns multi-service E2E orchestration scenarios.
9. **Unified NATS Messaging & TLS Transport Standard (`go/pkg/messaging`, `python/microservice_toolbox/messaging`, `rust/src/messaging`)**:
   - **Authoritative Subject Prefix**: Standardize subject routing on `bastien-antigravity`.
   - **Unified Connection Interface**: Broker connections must be initialized via `messaging.Connect` (Go), `connector.connect` (Python), or `connector::connect` (Rust), standardizing connection event logging, reconnect intervals, and heartbeat liveness options.
   - **Multi-Node Wire Security**: When `tls.enabled: true` or connecting outside `127.0.0.1` with certificate assets, connectors inject trusted root CAs and mTLS client certificates (`nats.RootCAs` / `nats.ClientCert` in Go, `ssl.SSLContext` in Python, `async_nats::ConnectOptions::require_tls` in Rust).
   - **Polyglot Scope Boundary**: C++ and VBA intentionally omit `messaging/` to avoid dead code and heavy external C runtime dependencies (`cnats`/`libuv`). C++ communicates via `SafeSocket` TCP (`conn_manager`) or direct gRPC alerts (`notification`), and VBA communicates via `NotificationClient`.
10. **Dedicated `AppConfig` Versioning Standard (`appConfig.GetVersion()` / `app_config.get_version()`)**:
    - **Single Canonical Accessor**: Microservices ALWAYS access their version through the dedicated method on the bootstrapped `AppConfig` object:
      - Go: `appConfig.GetVersion()`
      - Python: `app_config.get_version()` (or `app_config.version`)
      - Rust: `app_config.get_version()`
      - C++: `appConfig->GetVersion()` (or `appConfig.GetVersion()`)
      - VBA: `cfg.GetVersion()` (or `cfg.Version`)
    - **`VERSION.txt` ONLY**: Backed internally by `go/pkg/version`, `microservice_toolbox/version`, `rust/src/version`, `Version.hpp`, and `Toolbox.bas`, version resolution reads strictly from `VERSION.txt` (or build constants compiled directly from `VERSION.txt`), failing fast if missing — with zero runtime `APP_VERSION`/`SERVICE_VERSION` env overrides and zero `"0.0.1"` fallbacks.
    - **Zero Reinvention**: Microservices MUST NOT write bespoke `VERSION.txt` file-scanning loops (`[]string{"VERSION.txt", "../VERSION.txt"}`), hand-rolled env lookups, or direct internal `version` package boilerplate when `appConfig` is available. Hardcoding static versions in code or telemetry is strictly prohibited (`HARDCODED_VERSION_VIOLATION`).
11. **Standardized Declarative `ServiceSpec`, OpenMFE & Exchange Contracts (`spec` & `contracts` — Never Reimplement)**:
    - **Standard Tools Provide Metadata & Enrichment Automatically**: Calling `BuildSpecFromConfig` / `PublishWithLifecycle` automatically populates `Version` (via `appConfig.GetVersion()`), `URL` (from `rest_addr` / `listen_addr` in `AppConfig`), `DataStructure` (`version`, `capability`, `ports`, `node`), `%s` port substitution in `Framing`, `NavRoute`, `Canvas`, and `Health`. Do NOT manually hand-roll `VERSION.txt` reads, `os.Hostname()`, `SplitHostPort`, or custom HTTP `/api/v1/register` loops.
    - **Canonical API Access Across Languages**:
      - Go: `spec.PublishWithLifecycle(appConfig, logger, lm, capability, spec.ServiceSpec{...})` + `go/pkg/spec/contracts.go` (`ExchangeContract`, `ContractPeer`, `ContractOperation`, `NewContractsEnvelope`, `DisplayAddress`, `ResolveContractPort`, `ExtractProtoTextOperations`, `ExtractCapnpOperations`, `RenderProtoIDL`)
      - Python: `spec.publish_with_lifecycle(app_config, logger, lm, capability, spec=ServiceSpec(...))` + `microservice_toolbox.contracts` (`ExchangeContract`, `ContractsEnvelope`, `new_contracts_envelope`, `build_contracts_envelope`, `display_address`, `resolve_contract_port`, `extract_fastapi_operations`, `extract_proto_operations`, `extract_capnp_operations`)
      - Rust: `spec::publish_with_lifecycle(&app_config, logger, Some(&lm), capability, ServiceSpec{...})` + `microservice_toolbox::contracts` (`ExchangeContract`, `ContractsEnvelope`, `new_contracts_envelope`, `build_contracts_envelope`, `display_address`, `resolve_contract_port`, `extract_proto_operations`, `extract_capnp_operations`)
      - C++17: `SpecPublisher::PublishWithLifecycle(appConfig, logger, &lm, capability, ServiceSpec{...})` + `contracts.hpp` (`ExchangeContract`, `ContractsEnvelope`, `NewContractsEnvelope`, `BuildContractsEnvelope`, `DisplayAddress`, `ResolveContractPort`, `ExtractProtoTextOperations`, `ExtractCapnpOperations`)
      - C11/C99: `cpp/include/microservice_toolbox/spec/contracts.h` (`MtExchangeContract`, `MtContractsEnvelope`, `mt_exchange_contract_to_json`, `mt_contracts_envelope_to_json`, `mt_spec_free_string`)
    - **Microservice Specification & Contract Ownership**: Microservices declare their static identity metadata (`Name`, `Tag`, `Layer`, `Category`, `Description`, `DocLink`, `Protocol`, `Framing`) and build `ExchangeContract[]` descriptors using the toolbox extractors over embedded `.proto`, `.capnp`, SQL DDLs, and live routes/tools. HTTP-capable services expose `GET /api/v1/contracts` (`ContractsEnvelope`); non-HTTP services publish `ServiceSpec.Contracts` directly to `web-interface` (never fabricated in UI code).
    - **Platform Schema SSoT (`logger.capnp` & `notifier.capnp`)**: Canonical Cap'n Proto wire schemas reside exclusively in `microservice-toolbox` (`go/pkg/schemas/logger` `LoggerCapnpSchema`, `go/pkg/schemas/notifier` `NotifierCapnpSchema`, cross-language `schemas/platform/{logger,notifier}.capnp`, and Rust `microservice_toolbox::contracts::{LOGGER_CAPNP_SCHEMA, NOTIFIER_CAPNP_SCHEMA}`). Services pass these SSoT constants directly into `ExtractCapnpOperations` / `extract_capnp_operations` for dynamic `web-interface` contract inspection and MUST NEVER duplicate `logger.capnp` or `notifier.capnp` locally.
    - **Fail-Fast Synchronous Validation**: `PublishWithLifecycle` / `publish` strictly validates mandatory metadata synchronously on the cold startup path; missing metadata or unresolvable `web_interface` capability aborts boot immediately (fail-fast) before launching the background retry worker.
    - **Infinite Retry Background Registration**: Spec publication to `web-interface` runs in a non-blocking background thread/goroutine with exponential backoff and randomized jitter (`MaxRetries: -1`) so microservice boot never hangs on offline downstream UI dependencies.
12. **Real-Time Transport WireTap Standard (`go/pkg/wiretap`, `python/microservice_toolbox/wiretap.py`, `rust/src/wiretap/mod.rs`, `cpp/.../wiretap/WireTap.hpp`)**:
    - **Lock-Free Atomic Switch**: Controlled via `wiretap.SetEnabled(bool)` / `wiretap.IsEnabled()` (Go), `set_enabled(bool)` / `is_enabled()` (Python/Rust), and `SetEnabled(bool)` / `IsEnabled()` (C++). Configured via `common.wiretap_enabled` (or `local.wiretap_enabled`) in `AppConfig` and hot-reloadable at runtime via `OnLiveConfUpdate` or `web-interface` (`POST /api/v1/system/wiretap/toggle`).
    - **Zero-Fallback `AppConfig` Contract**: `ConfigureFromConfig` (Go/C++) and `configure_from_config` (Python/Rust/C++) MUST read pre-validated string parameters directly from `AppConfig` (`GetListenAddr("web_interface")`, `GetLocal("wiretap_enabled")`, `common.wiretap_enabled`). Never add defensive `hasattr` chains, `try/except: pass` blocks, `os.Getenv` overrides, or hardcoded `"http://127.0.0.1:5000"` fallbacks.
    - **Explicit Error Logging on Init**: In `python/microservice_toolbox/utils/init.py`, any exception during `configure_from_config` initialization MUST be logged via `logger.error(f"Failed to initialize WireTap transport telemetry: {e}")` — silent `except Exception: pass` is strictly prohibited.
    - **Automatic Multi-Transport Wiring**:
      - `bootstrap.BootstrapService` (Go) and `init_microservice` (Python) automatically initialize WireTap and bind the `safe-socket` telemetry hook (`safesocket.SetTelemetryHook`).
      - `go/pkg/teleremote` (`client.go`), `go/pkg/notification` (`client.go`), `go/pkg/network` (`grpc.go` unary and stream server interceptors), and `go/pkg/messaging` (`connector.go` NATS wrapper) automatically emit real-time `EdgeReport`s with segregated sub-channels (`ChannelStat` with `frames` and `bytes`) when WireTap is enabled.
      - External clients and gateways (such as `antigravity_ide` MCP requests in `09-RAG-Engine` and `telegram_cloud` Bot API calls in `tele-remote` / `notif-server`) report live edges with `Layer: "EXT"`.


