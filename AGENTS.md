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

