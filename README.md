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

A unified infrastructure library for the Bastien-Antigravity microservices ecosystem. Supporting Go, Python, and Rust.

## Core Features

### 1. Smart Configuration Loader
Implements a strict "Hierarchy of Truth" for service configuration:
1.  **Command Line Overrides** (`--params`, `--host`, `--port`, `--grpc_host`, `--grpc_port`): Highest Priority.
2.  **Local File Override** (`[profile].yaml`): Authritative local source (overrides Server).
3.  **Config Server Baseline**: Fleet configuration.
4.  **Environment Variables**: Base layer (lowest priority).

### 2. Network-Aware Resolver & Docker Guard
*   **Docker Detection**: Automatically resolves `127.0.0.x` loopback addresses to the internal container interface.
*   **Docker Guard**: CLI overrides for networking (`--host`, `--port`, `--grpc_host`, `--grpc_port`) are **ignored** in containerized environments. This ensures inter-service connectivity is never broken by manual runtime overrides.

### 3. Unified gRPC Foundation
Standardized gRPC infrastructure across all three languages:
- **Consistent Addressing**: Unified `GetGRPCListenAddr` helpers.
- **Graceful Lifecycle**: `GRPCServer` wrappers with built-in reflection and graceful shutdown logic.

### 4. Universal Serializers
Standardized serialization interfaces for seamless data exchange:
- **JSON**: Cross-platform JSON encoding/decoding.
- **Binary**: All three languages use **msgpack** for cross-language binary serialization (`msgpack/v5` in Go, `msgpack` in Python, `rmp-serde` in Rust) for high-performance internal tasks.
- **API Parity**: Identical `marshal` and `unmarshal` signatures across all languages.

### 5. Reliable Connection Manager (`conn_manager`)
A robust connection wrapper designed for microservice resilience:
- **Advanced Retry Strategy**: Supports multiplicative backoff and randomized jitter to prevent "thundering herd" issues.
- **Connection Modes**:
    - `ModeBlocking`: Blocks until initial connection succeeds or retries are exhausted.
    - `ModeNonBlocking`: Returns immediately and connects in the background (ideal for high-perf apps).
    - `ModeIndefinite`: Blocks forever until the connection is established (ideal for audit/critical apps).
- **Strategy Presets**: Standardized configurations for `Critical`, `Standard`, and `Performance` scenarios.
- **Transparent Reconnection**: Automatically handles reconnections during write failures.

---

## Language Support

### Go
Located in `/go`.
```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/conn_manager"
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/serializers"

// 1. Initialize with a Standard Strategy
nm := conn_manager.NewStandardStrategy(nil)
nm.OnError = func(attempt int, err error, source string, msg string) {
    if attempt == nm.MaxRetries {
        fmt.Printf("Final failure after %d attempts: %v\n", attempt, err)
    }
}

// 2. Connect using a specific mode
conn := nm.Connect(&ip, &port, &publicIP, "my-profile", conn_manager.ModeBlocking)
defer conn.Close()
```

### Python
Located in `/python`.
```python
from microservice_toolbox.conn_manager import new_network_manager
from microservice_toolbox.serializers.providers import JSONSerializer

# 1. Initialize with a Performance Strategy
from microservice_toolbox.conn_manager import new_performance_strategy, ConnectionMode

nm = new_performance_strategy()

# 2. Connect in the background
conn = nm.connect("127.0.0.1", "8080", "1.2.3.4", "test", ConnectionMode.NON_BLOCKING)

# 2. Use Serializers
serializer = JSONSerializer()
payload = serializer.marshal({"status": "ok"})
```

### Rust
Located in `/rust`.
```rust
use microservice_toolbox::conn_manager::manager::new_network_manager_with_all;
use microservice_toolbox::serializers::providers::{JsonSerializer};
use std::sync::Arc;

// 1. Initialize with a Critical Strategy
use microservice_toolbox::conn_manager::manager::{NetworkManager, ConnectionMode};
let nm = NetworkManager::new_critical(None);

// 2. Connect indefinitely (blocks until success)
let conn = nm.connect("127.0.0.1".into(), "8080".into(), ConnectionMode::Indefinite).await;

// 2. Use Serializers
let ser = JsonSerializer::new(); // returns SerializerEnum
let bytes = ser.marshal(&my_struct)?;
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
