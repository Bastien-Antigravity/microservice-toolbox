---
tags:
- '#ai/ignore'
- '#domain/testing'
- '#zone/3-fleet'
---

# 🧪 Testing Playbook

## Comprehensive Verification Framework
The `microservice-toolbox` is guarded by a multi-layered verification framework ensuring feature parity and stability across all supported languages.

### 1. Go Unit Testing
Ensures reference logic correctness for the core engine:
- **Framework**: `testing` (Standard Library) + `testify/assert`.
- **Command**: `cd go && go test -v ./pkg/...`
- **Key Focus**: Config layering, deep merging, TCP connection management, and **MsgPack/JSON round-trips**.

### 2. Python Unit Testing
Validates wrapper logic and pythonic type conversions using `pytest`:
- **Framework**: `pytest`.
- **Command**: `cd python && pytest`
- **Key Focus**: Type-hint validation, `input_args` decoupling, and async-compatible connection logic.

### 3. Rust Unit Testing
Verifies memory-safe Cargo compilation and unit coverage:
- **Framework**: Native `cargo test`.
- **Command**: `cd rust && cargo test`
- **Key Focus**: Thread-safety (`Arc/Mutex`), `tokio` async task management, and `serde` compatibility.
- **On-Demand RSA**: Verified explicit decryption parity with Go and Python.

### 4. C++ Parity Testing
Validates C++ headers and dynamic link capabilities:
- **Command**: `cd cpp && make test`
- **Key Focus**: Parity with Go-bridge expansion logic and JSON mirroring.

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
