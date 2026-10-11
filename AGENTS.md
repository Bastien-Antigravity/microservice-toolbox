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
  - `go/pkg/logger`: Unified ILogger abstraction compatible with universal-logger
  - `go/pkg/messaging`: Resilient NATS Core and JetStream connection manager
  - `go/pkg/notification`: Direct multi-channel notification client facade for L2/L3 services (gRPC port 1027 to notif-server)
  - `go/pkg/utils`: Terminal UI helpers, environment and formatting utilities
- **Configuration Link**: `standalone.yaml -> ../docker-deployment/modes/local/config/native.yaml`

## Key Build & Test Commands
```bash
# Test Go package
go test -v ./go/...

# Test Python bindings
pytest python/

# Test Rust crate
cd rust && cargo test
```

## AI Development & Integration Guidelines
1. **API Parity Across Languages**: Maintain conceptual and naming symmetry between Go, Python, and Rust implementations.
2. **Never Bypass Engine Abstractions**: Go implementations wrap `distributed-config` and `universal-logger`. Do not introduce redundant config parsing.
3. **Graceful Degradation**: Bootstrap must yield informative diagnostic logs when configurations or capabilities cannot be located.
4. **Header Ritual**: All source files MUST contain the Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
5. **Section Dividers**: Use appropriate section dividers (`// ----...` for Go/Rust/C++, `# ----...` for Python).
6. **Two-Tier Logging & EnsureSafeLogger Standard**:
   - **Tier 1 (Libraries & Reusable SDKs)**: Reusable components and constructors across Go, Python, Rust, and C++ (`safe-socket`, `distributed-config`, `conn_manager`, `teleremote`, etc.) wrap injected loggers using `EnsureSafeLogger(l)` / `ensure_safe_logger(l)` to prevent nil pointer panics and eliminate repetitive `if logger != nil` branches.
   - **Tier 2 (Microservices)**: Production microservice entry points must initialize via `BootstrapService`, which guarantees a non-nil `ILogger`. Calling `EnsureSafeLogger` or using no-op fallbacks in non-test microservice source code is strictly prohibited (`PRODUCTION_MOCK_POLLUTION`).
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

