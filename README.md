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

---

## Language Support

### Go
Located in `/go`.
```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/network"

// 1. Load Config
ac, _ := config.LoadConfig("standalone", nil)
addr, _ := ac.GetGRPCListenAddr("my_service")

// 2. Start Standard Server
server := network.NewGRPCServer(addr)
server.Start(your_servicer_registration_func)
```

### Python
Located in `/python`.
```python
from microservice_toolbox.config.loader import load_config
from microservice_toolbox.network.grpc_server import GRPCServer

# 1. Load Config
ac = load_config("standalone")
addr = ac.get_grpc_listen_addr("my_service")

# 2. Start Server
server = GRPCServer(addr)
server.add_service(add_MyService_to_server, MyServicer())
server.start()
```

### Rust
Located in `/rust`.
```rust
use microservice_toolbox::config::loader::load_config;
use microservice_toolbox::network::grpc_server::GrpcServer;

// 1. Load Config
let ac = load_config("standalone");
let addr = ac.get_grpc_listen_addr("my_service")?;

// 2. Start Fluent Server
let server = GrpcServer::new(&addr, DESCRIPTOR_SET);
server.add_service(MyServiceServer::new(service)).start().await?;
```

## Security Best Practices
Services using this toolbox should NOT publish internal ports in `docker-compose.yaml`. Inter-service discovery is handled via the internal `teleremote_network` using service names.
