# Testing Strategy: Microservice Toolbox

The `microservice-toolbox` uses a multi-layered testing strategy to ensure reliability across Go, Python, and Rust.

## 1. Unit Testing (Localized)

Each language module maintains its own suite of unit tests focusing on internal logic, edge cases, and API compliance.

### Go (`/go`)
- **Framework**: `testing` (Standard Library) + `testify/assert`.
- **Command**: `go test -v ./pkg/...`
- **Focus**: Config layering, deep merging, TCP connection management, and MsgPack/JSON round-trips.

### Python (`/python`)
- **Framework**: `pytest`.
- **Command**: `pytest python/tests`
- **Focus**: Type-hint validation, `input_args` decoupling, and async-compatible connection logic.

### Rust (`/rust`)
- **Framework**: Native `cargo test`.
- **Command**: `cargo test`
- **Focus**: Thread-safety (`Arc/Mutex`), `tokio` async task management, and `serde` compatibility.

---

## 2. Cross-Language Integration Testing (`/integration`)

To ensure that data serialized in one language is perfectly consumable by another, we use a dedicated **Compatibility Matrix** test.

### The Matrix Test
We validate the following interactions for both **JSON** and **MsgPack**:
- **Go** $\rightarrow$ **Python**
- **Go** $\rightarrow$ **Rust**
- **Rust** $\rightarrow$ **Python**
- **Rust** $\rightarrow$ **Go**
- **Python** $\rightarrow$ **Go/Rust**

### Running the Suite
```bash
./integration/run_tests.sh
```
This script automates the generation of binary/text payloads from each language and executes the corresponding consumers in the others.

---

## 3. Continuous Integration (CI)

All tests are automatically executed on every push and pull request via GitHub Actions (`.github/workflows/ci.yml`).

### CI Build Gate
- **Linting**: `golangci-lint` (Go), `ruff` (Python), `cargo fmt` (Rust).
- **Unit Tests**: Full suite execution in isolated Ubuntu containers.
- **Integration Tests**: The complete cross-language matrix must pass before merging.
