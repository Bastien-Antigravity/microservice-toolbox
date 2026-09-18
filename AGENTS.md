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
