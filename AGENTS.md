# AGENTS.md: microservice-toolbox

## Service Mission & Architecture Role
`microservice-toolbox` is the canonical, cross-language developer framework and facade for the Bastien-Antigravity ecosystem. It standardizes service initialization (`BootstrapService`), configuration loading (wrapping `distributed-config`), logging setup (wrapping `universal-logger`), lifecycle management, and inter-service client connectivity across Go, Python, Rust, C++, and VBA.

- **Ecosystem Role**: Universal Facade and SDK.
- **Sub-packages (Go)**:
  - `go/pkg/bootstrap`: Single-call service initialization (`BootstrapService`, `BootstrapServiceSafe`)
  - `go/pkg/config`: Layered configuration management (`LoadConfig`, CLI overrides, port validation)
  - `go/pkg/conn_manager`: Resilient network connections with backoff and retry policies
  - `go/pkg/connectivity`: Dynamic address resolution and Docker Guard network suppression
  - `go/pkg/lifecycle`: Graceful shutdown management (`Manager.Wait`), OS signal trapping (SIGINT/SIGTERM)
  - `go/pkg/network`: gRPC server builder with Docker Guard integration
  - `go/pkg/serializers`: Unified JSON and MsgPack binary serialization
  - `go/pkg/business`: Canonical market domain models (MarketEvent, OHLCV, Signal)
  - `go/pkg/teleremote`: Telegram bot client facade and menu tree builder
  - `go/pkg/logger`: Unified Logger abstraction compatible with universal-logger
  - `go/pkg/messaging`: Resilient NATS Core and JetStream connection manager
  - `go/pkg/notification`: Direct multi-channel notification client facade for L2/L3 services (gRPC port 1027 to notif-server)
  - `go/pkg/utils`: Terminal UI helpers, environment and formatting utilities
  - `go/pkg/version`: Standardized dynamic semver resolution adhering to VERSION.txt
  - `go/pkg/spec`: Canonical declarative service specification, OpenMFE registration, and Exchange Contract models/extractors (`contracts.go`)
  - `go/pkg/wiretap`: Lock-free real-time transport telemetry aggregator (`SafeSocket`, gRPC, NATS, HTTP, MCP)
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
3. **Graceful Degradation**: Bootstrap must yield informative diagnostic logs when configurations or capabilities cannot be located.
4. **Header Ritual**: All source files MUST contain the Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
5. **Section Dividers**: Use appropriate section dividers (`// ----...` for Go/Rust/C++, `# ----...` for Python).
6. **Two-Tier Logging & EnsureSafeLogger Standard**:
   - **Tier 1 (Libraries & Reusable SDKs)**: Reusable components and constructors across Go, Python, Rust, and C++ (`safe-socket`, `distributed-config`, `conn_manager`, `teleremote`, etc.) wrap injected loggers using `EnsureSafeLogger(l)` / `ensure_safe_logger(l)` to prevent nil pointer panics and eliminate repetitive `if logger != nil` branches.
   - **Tier 2 (Microservices)**: Production microservice entry points must initialize via `BootstrapService`, which guarantees a non-nil `Logger`. Calling `EnsureSafeLogger` or using no-op fallbacks in non-test microservice source code is strictly prohibited (`PRODUCTION_MOCK_POLLUTION`).
   - **Strict Mode Enforcement**: When `STRICT_LOGGER=true`, `EnsureSafeLogger` panics / raises `RuntimeError` immediately upon receiving `nil`, ensuring uninitialized dependencies fail-fast on boot rather than running dark.
7. **L1 Resilience, Connectivity & Self-Healing Contract**:
   - All inter-service connections must leverage `conn_manager`, `teleremote`, or `messaging` with infinite retries (`MaxRetries: -1` in `NewCriticalStrategy`) and exponential backoff with randomized jitter (`GetNextDelay`). Infinite retry is a design requirement for autonomous recovery.
   - Non-blocking execution (`ModeNonBlocking`) is mandatory for peripheral discovery and registration hooks (such as OpenMFE) so microservice boot never hangs on offline downstream dependencies.
   - Address resolution must utilize `connectivity.Resolver` / `appConfig.GetListenAddr(...)` to honor Docker Guard (`0.0.0.0` in container environments) while preserving native localhost addresses.
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
10. **Standardized Dynamic Versioning Engine (`go/pkg/version`, `python/microservice_toolbox/version`, `rust/src/version`, `cpp/.../version/Version.hpp`, `vba/Toolbox.bas`)**:
    - **Single Source of Truth**: Resolves dynamic semver strictly from `VERSION.txt` at the repository root via upward directory traversal, environment variable overrides (`APP_VERSION`, `SERVICE_VERSION`), and compile-time LDFLAGS injection (`BuildVersion` / macro `APP_VERSION`).
    - **Canonical API Access**:
      - Go: `appConfig.GetVersion()` or `version.Get()`
      - Python: `app_config.get_version()` or `microservice_toolbox.get_version()`
      - Rust: `app_config.get_version()` or `microservice_toolbox::version::get_version()`
      - C++: `appConfig.GetVersion()` or `microservice_toolbox::version::GetVersion()`
      - VBA: `cfg.GetVersion()` / `cfg.Version` or `Toolbox.GetVersion()`
    - **Zero Ad-Hoc Scanning Loops**: Microservices MUST NOT write bespoke directory searching loops or relative path slices (e.g. `[]string{"VERSION.txt", "../VERSION.txt"}`). Hardcoding version numbers in code or status responses is strictly prohibited (`HARDCODED_VERSION_VIOLATION`).
11. **Standardized Declarative Service Specification, OpenMFE & Exchange Contracts (`go/pkg/spec`, `python/microservice_toolbox/contracts.py`, `rust/src/spec.rs`, `cpp/.../spec/spec.hpp`, `contracts.hpp`, `contracts.h`)**:
    - **Canonical API Access Across Languages**:
      - Go: `spec.PublishWithLifecycle(appConfig, logger, lm, capability, spec.ServiceSpec{...})` + `spec.ExchangeContract` / `spec.NewContractsEnvelope`
      - Python: `spec.publish_with_lifecycle(app_config, logger, lm, capability, spec=ServiceSpec(...))` + `contracts.ExchangeContract` / `contracts.build_contracts_envelope`
      - Rust: `spec::publish_with_lifecycle(&app_config, logger, Some(&lm), capability, ServiceSpec{...})` + `spec::ExchangeContract`
      - C++: `SpecPublisher::PublishWithLifecycle(appConfig, logger, &lm, capability, ServiceSpec{...})` + `contracts.hpp` (`ExchangeContract`, `ContractsEnvelope`, `ExtractProtoTextOperations`, `ExtractCapnpOperations`)
      - C11/C99: `cpp/include/microservice_toolbox/spec/contracts.h` (`MtExchangeContract`, `MtContractsEnvelope`, `mt_contracts_envelope_to_json`, `mt_spec_free_string`)
    - **Microservice Specification & Contract Ownership**: Microservices are the authoritative source of truth for their own metadata (`Name`, `Tag`, `URL`, `Layer`, `Category`, `Description`, `DocLink`, `Protocol`, `Framing`) and their `ExchangeContract[]` descriptors (derived from embedded `.proto`, `.capnp`, SQL DDLs, and live route/tool introspection). HTTP-capable services expose `GET /api/v1/contracts` (`ContractsEnvelope`); non-HTTP services publish `ServiceSpec.Contracts` cleanly to `web-interface` (never fabricated in UI code).
    - **Fail-Fast Synchronous Validation**: `PublishWithLifecycle` / `publish` strictly validates mandatory metadata synchronously on startup; missing metadata or unresolvable `web_interface` capability aborts boot immediately (fail-fast) before launching the background retry worker.
    - **Infinite Retry Background Registration**: Spec publication to `web-interface` runs in a non-blocking background thread/goroutine with exponential backoff and randomized jitter, adhering to the L1 Resilience Contract so microservice boot never hangs on offline downstream UI dependencies.
12. **Real-Time Transport WireTap Standard (`go/pkg/wiretap`, `python/microservice_toolbox/wiretap.py`)**:
    - **Lock-Free Atomic Switch**: Controlled via `wiretap.SetEnabled(bool)` / `wiretap.IsEnabled()` (Go `sync/atomic.Bool`, simultaneously toggling `safesocket.SetTelemetryEnabled`) and `set_enabled(bool)` / `is_enabled()` (Python). Configured via `common.wiretap_enabled` (or `local.wiretap_enabled`) in `AppConfig` and hot-reloadable at runtime via `OnLiveConfUpdate` or the `web-interface` canvas toggle (`POST /api/v1/system/wiretap/toggle`).
    - **Zero-Fallback `AppConfig` Contract**: `ConfigureFromConfig` (Go) and `configure_from_config` (Python) MUST read pre-validated string parameters directly from `AppConfig` (`appConfig.GetListenAddr("web_interface")`, `appConfig.GetLocal("wiretap_enabled")`, `appConfig.Config.Common["wiretap_enabled"]`). Never add defensive `hasattr` chains, `try/except: pass` blocks, `os.Getenv` overrides, hardcoded `"http://127.0.0.1:5000"` fallbacks, or hardcoded default port maps.
    - **Explicit Error Logging on Init**: In `python/microservice_toolbox/utils/init.py`, any exception during `configure_from_config` initialization MUST be logged via `logger.error(f"Failed to initialize WireTap transport telemetry: {e}")` — silent `except Exception: pass` is strictly prohibited.
    - **Automatic Multi-Transport Wiring**:
      - `bootstrap.BootstrapService` (Go) and `init_microservice` (Python) automatically initialize WireTap and bind the `safe-socket` telemetry hook (`safesocket.SetTelemetryHook`).
      - `go/pkg/teleremote` (`client.go`), `go/pkg/notification` (`client.go`), `go/pkg/network` (`grpc.go` unary and stream server interceptors), and `go/pkg/messaging` (`connector.go` NATS wrapper) automatically emit real-time `EdgeReport`s with segregated sub-channels (`ChannelStat` with `frames` and `bytes`) when WireTap is enabled.
      - External clients and gateways (such as `antigravity_ide` MCP requests in `09-RAG-Engine` and `telegram_cloud` Bot API calls in `tele-remote` / `notif-server`) report live edges with `Layer: "EXT"`.


