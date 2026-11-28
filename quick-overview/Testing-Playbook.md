---
microservice: microservice-toolbox
type: testing-playbook
status: active
language: polyglot
tags:
- '#service/microservice-toolbox'
- '#type/testing-playbook'
- '#state/active'
- '#ai/ignore'
- '#zone/3-fleet'
---
# 🧪 Testing Playbook

## Comprehensive Verification Framework
The `microservice-toolbox` is guarded by a multi-layered verification framework ensuring feature parity and stability across all supported languages.

### 1. Go Unit Testing
Ensures reference logic correctness for the core engine:
- **Framework**: `testing` (Standard Library) + `testify/assert`.
- **Command**: `cd go && go test -count=1 -v -race ./pkg/...` (or from `microservice-toolbox/` root: `go test -count=1 -v -race ./go/...`)
- **Key Focus**: Config layering, deep merging, TCP connection management, and **MsgPack/JSON round-trips**.

### 2. Python Unit Testing
Validates wrapper logic and pythonic type conversions using `pytest`:
- **Framework**: `pytest`.
- **Command**: `cd python && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest` (or `pytest tests`)
- **Key Focus**: Type-hint validation, `input_args` decoupling, `ExchangeContract` extractors, `WireTap`, `version` fail-fast checks, and async connection logic.

### 3. Rust Unit Testing
Verifies memory-safe Cargo compilation and unit coverage:
- **Framework**: Native `cargo test`.
- **Command**: `cd rust && cargo test`
- **Key Focus**: Thread-safety (`Arc/Mutex`), `tokio` async task management, and `serde` compatibility.
- **On-Demand RSA**: Verified explicit decryption parity with Go and Python.

### 4. C++17 & C11 Parity Testing
Validates C++17 headers, pure C11 contract headers, and `libdistconf`/`libnotif` FFI links:
- **Command**: `make -C cpp test && make -C cpp clean`
- **Key Focus**: `test_config`, `test_modules` (Connectivity, Lifecycle, Business, Serializers, Logger, WireTap), `test_notification`, `test_version`, `test_spec`, and `test_contracts_c` (`-std=c11 -Werror`).

### 5. Multi-Language Serialization Integration Matrix
This suite validates cross-language roundtrip capability. The generator-consumer matrix (Go ⇄ Python ⇄ Rust) tests serialization using both JSON and MessagePack.

```bash
./integration/run_tests.sh
```

**Compatibility Matrix Coverage (JSON & MsgPack):**
- **Go** $\rightarrow$ **Python** / **Python** $\rightarrow$ **Go**
- **Go** $\rightarrow$ **Rust** / **Rust** $\rightarrow$ **Go**
- **Rust** $\rightarrow$ **Python** / **Python** $\rightarrow$ **Rust**

## CI/CD Integration
The entire pipeline is automated via GitHub Actions (`.github/workflows/ci.yml`). 

### CI Build Gates
- **Linting**: `golangci-lint` (Go), `ruff` (Python), `cargo fmt` (Rust).
- **Isolated Execution**: Unit tests are executed in isolated Ubuntu containers to ensure environment consistency.
- **Gatekeeper**: The complete cross-language matrix must pass with a "SUCCESS" status before any pull request is merged.
