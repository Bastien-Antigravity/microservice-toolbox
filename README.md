---
microservice: microservice-toolbox
type: repository
status: active
language: polyglot
tags:
- '#service/microservice-toolbox'
- '#domain/architecture'
- '#domain/configuration'
- '#zone/3-fleet'
---

# Microservice Toolbox

A unified infrastructure library for the Bastien-Antigravity microservices ecosystem. Supporting **Go, Python, Rust, C++, and VBA**.

## 📚 Documentation Index
- **[Architecture Overview](quick-overview/Architecture-Overview.md)**: System design, FFI bridging, and repository anatomy.
- **[Features & Behavior](quick-overview/Features-Behavior.md)**: Configuration hierarchy, secret management, and data standards.
- **[Testing Playbook](quick-overview/Testing-Playbook.md)**: Unit tests, integration matrix, and CI/CD validation.

---

## 🏗️ Executive Summary
The `microservice-toolbox` provides common operational patterns for the Bastien-Antigravity fleet. It ensures that regardless of the language used, all microservices share identical configuration resolution, security boundaries, and data models.

## Core Features

### 1. Smart Configuration Loader
Implements a strict "Hierarchy of Truth" for service configuration:
1.  **Command Line Overrides** (`--key`, `--host`, `--port`): Highest Priority. 
2.  **Environment Variables** (`BASTIEN_PRIVATE_KEY_PATH`): OS-level overrides.
3.  **Local File Override** (`[profile].yaml`): Authoritative local source.
4.  **Config Server Baseline**: Fleet configuration baseline.

> [!NOTE]
> **Universal Override Policy**: The local file override acts as an authoritative, unconditional override across all profiles (including production and staging) to ensure absolute local alignment.

### 2. Local Configuration Namespace (`Local`)
Every implementation supports the `local:` YAML section for service-specific settings that are **never** synchronized to the fleet.
- **Go/Python/Rust**: Support `UnmarshalLocal()` to map settings directly to language-native structures.
- **Error Transparency (v0.0.1+)**: All toolboxes support raw error pass-through via the `GetLastError()` API.

### 3. RSA Secret Management (v0.0.1+)
Standardized on-demand secret decryption engine across the ecosystem:
- **On-Demand Decryption**: Secrets remain encrypted as `ENC(...)` in memory. Call `DecryptSecret()` to get the plaintext.
- **Centralized Security**: Decryption logic is centralized in the Go core; all other languages (Python, Rust, C++, VBA) bridge to this core for maximum security.
- **FFI Bridge Sync**: High-performance in-memory mirroring ensures sub-millisecond lookups in all languages.

### 4. Business Data Standards (v0.0.1+)
Unified data models for the business logic tier, defined in `schemas/business` and implemented in Go (`pkg/business`):
- **MarketEvent**: Low-latency envelope for L1/L2 data.
- **OHLCV**: Standardized time-series bar representation.
- **Signal**: Unified trading strategy signal format (Buy/Sell/Exit).

---

## Polyglot Parity Matrix

| Feature | Go | Python | Rust | C++ | VBA |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Layered YAML Loading | ✅ | ✅ | ✅ | ✅ | ✅ |
| CLI Flag Overrides (`--key`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Environment Var Expansion | ✅ | ✅ | ✅ | ✅ | ✅ |
| RSA Secret Decryption | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Error Transparency** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **In-Memory Mirroring** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **UnmarshalLocal** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Business Data Models**| ✅ | ✅ | ✅ | ✅ | ❌ |
| Connection Manager | ✅ | ✅ | ✅ | ✅ | ❌ |

---

## Polyglot Parity Rules
To ensure the ecosystem remains unified, all contributions to this toolbox must follow these rules:
1. **The Mirroring Mandate**: New features added to the Go (Reference) implementation must be ported to Python, Rust, and C++ in the same PR/cycle.
2. **Behavioral Identity**: Logic and error handling must be identical across all languages.
3. **Semantic Naming**: Use language-appropriate casing (`PascalCase` for Go, `snake_case` for Python/Rust), but the semantic name must be identical (e.g., `GetListenAddr` vs `get_listen_addr`).
4. **Integration Validation**: All changes must pass the `integration/run_tests.sh` matrix.

---

## Language Support

### C++
Located in `/cpp`. Uses `nlohmann/json` for high-speed mirroring.
```cpp
auto ac = LoadConfig("standalone");
std::string addr = ac->GetListenAddr("svc");
std::string secret = ac->DecryptSecret("ENC(...)");
```

### VBA
Located in `/vba`. Enabling Excel/Access integration.
```vba
Dim ac As New AppConfig
ac.Init "standalone"
Debug.Print ac.GetListenAddr("svc")
```

### Rust
Located in `/rust`. Type-safe configuration via `serde`.
```rust
let ac = AppConfig::load_config("standalone", None)?;
let cfg: MyLocalConfig = ac.unmarshal_local()?;
```

### Python
Located in `/python`. Pythonic wrappers with `ctypes` FFI.
```python
cfg = load_config("standalone")
secret = cfg.decrypt_secret("ENC(...)")
```

### Go
Located in `/go`. The reference implementation.
```go
cfg := config.LoadConfig("standalone")
addr := cfg.GetListenAddr("svc")
```

---

## Development & Testing

This repository uses a comprehensive, cross-language test suite to ensure architectural parity.

### Running Unit Tests
- **Go**: `cd go && go test ./...`
- **Python**: `cd python && pytest` (requires `ruff` for linting)
- **Rust**: `cd rust && cargo test`

### Integration Tests
Cross-language compatibility (e.g., Go -> Python serialization) is validated via the integration runner:
```bash
chmod +x integration/run_tests.sh
./integration/run_tests.sh
```

### CI/CD
All pull requests and pushes to `main` or `develop` are automatically validated via GitHub Actions in `.github/workflows/ci.yml`. This includes:
- Parallel Test & Linting for Go, Python, and Rust.
- Execution of the cross-language integration suite.

## Security Best Practices
Services using this toolbox should NOT publish internal ports in `docker-compose.yaml`. Inter-service discovery is handled via the internal `teleremote_network` using service names.
