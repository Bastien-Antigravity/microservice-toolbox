---
microservice: microservice-toolbox
type: repository
status: active
language: polyglot
tags:
  - domain/architecture
  - domain/configuration
---

# Microservice Toolbox

A unified infrastructure library for the Bastien-Antigravity microservices ecosystem. Supporting **Go, Python, Rust, C++, and VBA**.

## Core Features

### 1. Smart Configuration Loader
Implements a strict "Hierarchy of Truth" for service configuration:
1.  **Command Line Overrides** (`--key`, `--host`, `--port`, ): Highest Priority.
2.  **Environment Variables** (`BASTIEN_PRIVATE_KEY_PATH`): OS-level overrides.
3.  **Local File Override** (`[profile].yaml`): Authoritative local source.
4.  **Config Server Baseline**: Fleet configuration.

### 2. Local Configuration Namespace (`Local`)
Every implementation supports the `Local` configuration block (parsed from the `local:` YAML section). This is reserved for service-specific settings that are **never** synchronized to the fleet.
- **Go/Python/Rust**: Support `UnmarshalLocal()` to map settings directly to language-native structs/classes.
- **Transparency (v1.9.9+)**: All toolboxes now support raw error pass-through via the `GetLastError()` API, ensuring engine-level failures are visible to the caller.

### 3. RSA Secret Management (v1.2.2+)
Standardized on-demand secret decryption engine across the ecosystem:
- **On-Demand Decryption**: Secrets remain encrypted as `ENC(...)` in memory. Call `DecryptSecret()` to get the plaintext.
- **Centralized Security**: Decryption logic is centralized in the Go core; all other languages (Python, Rust, C++, VBA) bridge to this core for maximum security.
- **FFI Bridge Sync**: High-performance in-memory mirroring ensures sub-millisecond lookups in all languages.

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
| Connection Manager | ✅ | ✅ | ✅ | ❌ | ❌ |

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
