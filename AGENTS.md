# AGENTS.md: microservice-toolbox

## Service Mission & Architecture Role
`microservice-toolbox` is the canonical, cross-language developer framework and facade for the Bastien-Antigravity ecosystem. It standardizes service initialization (`BootstrapService`), configuration loading (wrapping `distributed-config`), logging setup (wrapping `universal-logger`), lifecycle management, and inter-service client connectivity across Go, Python, Rust, C++, and VBA.

- **Ecosystem Role**: Universal Facade and SDK.
- **Sub-packages (Go)**:
  - `go/pkg/bootstrap`: Single-call service initialization (`BootstrapService`)
  - `go/pkg/lifecycle`: OS signal handling (`SignalContext`), shutdown hooks
  - `go/pkg/resilience`: Circuit breakers, retry policies
  - `go/pkg/timeseries`: TimescaleDB connection and query helpers
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
