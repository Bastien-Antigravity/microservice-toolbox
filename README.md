# Microservice Toolbox

A unified infrastructure library for the Bastien-Antigravity microservices ecosystem. Supporting Go, Python, and Rust.

## Core Features

### 1. Smart Configuration Loader
Implements a strict "Hierarchy of Truth" for service configuration:
1.  **Command Line Overrides** (`--params`, `--host`, `--port`, `--grpc_host`, `--grpc_port`): Highest Priority.
2.  **Context-Aware Overrides**:
    *   **Dev Mode** (`standalone`, `test`): Local File > Config Server.
    *   **Fleet Mode** (`production`, `preprod`): Config Server > Local File.
3.  **Environment Variables**: Base layer (lowest priority).

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
- **Binary**: Language-specific binary formats (`gob` in Go, `pickle` in Python, `bincode` in Rust) for high-performance internal tasks.
- **API Parity**: Identical `marshal` and `unmarshal` signatures across all languages.

### 5. Reliable Connection Manager (`conn_manager`)
A robust connection wrapper designed for microservice resilience:
- **Advanced Retry Strategy**: Supports multiplicative backoff and randomized jitter to prevent "thundering herd" issues.
- **Infinite Retries**: Option to retry indefinitely (`max_retries = -1`) for critical background services.
- **Transparent Reconnection**: Automatically handles reconnections during write failures.

---

## Language Support

### Go
Located in `/go`.
```go
import "github.com/Bastien-Antigravity/microservice-toolbox/pkg/conn_manager"
import "github.com/Bastien-Antigravity/microservice-toolbox/pkg/serializers"

// 1. Initialize Connection Manager (indefinite retry with jitter)
nm := conn_manager.NewNetworkManager(-1, 200, 5000, 2000, 2.0, 0.1)

// 2. Use Serializers
jsonSer := serializers.NewJSONSerializer()
data, _ := jsonSer.Marshal(myObj)
```

### Python
Located in `/python`.
```python
from microservice_toolbox.conn_manager.manager import NewNetworkManager
from microservice_toolbox.serializers.providers import JSONSerializer

# 1. Initialize Connection Manager
nm = NewNetworkManager(max_retries=5, base_delay_ms=200, backoff=2.0, jitter=0.1)

# 2. Use Serializers
serializer = JSONSerializer()
payload = serializer.marshal({"status": "ok"})
```

### Rust
Located in `/rust`.
```rust
use microservice_toolbox::conn_manager::manager::new_network_manager;
use microservice_toolbox::serializers::providers::JsonSerializer;

// 1. Initialize Async Connection Manager
let nm = new_network_manager(5, 200, 5000, 2000, 2.0, 0.1);

// 2. Use Serializers
let ser = JsonSerializer::new();
let bytes = ser.marshal(&my_struct)?;
```

## Security Best Practices
Services using this toolbox should NOT publish internal ports in `docker-compose.yaml`. Inter-service discovery is handled via the internal `teleremote_network` using service names.
