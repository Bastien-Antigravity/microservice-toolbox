# Microservice Toolbox

A unified infrastructure library for the Bastien-Antigravity microservices ecosystem. Supporting Go, Python, and Rust.

## Core Features

### 1. Smart Configuration Loader
Implements a strict "Hierarchy of Truth" for service configuration:
1.  **Command Line Overrides** (`--params`): Highest Priority. Always wins.
2.  **Context-Aware Overrides**:
    *   **Dev Mode** (`standalone`, `test`): Local File > Config Server.
    *   **Fleet Mode** (`production`, `preprod`): Config Server > Local File.
3.  **Environment Variables**: Base layer (lowest priority).

### 2. Network-Aware Resolver (Option 3)
Automatically detects the runtime environment to solve "Connection Refused" issues:
*   **Docker Detection**: Automatically resolves `127.0.0.x` loopback addresses to the internal container interface (e.g., `eth0`).
*   **Docker Guard**: CLI overrides for `--host` and `--port` are ignored in containerized environments to prevent breaking container network isolation.

### 3. Unified Lifecycle Management
Standardized graceful shutdown handling across all languages using a `LifecycleManager`.

## Language Support

### Go
Located in `/go`.
```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

// Initialize with profile and optional specific flags
ac, err := config.LoadConfig("standalone", []string{"my_flag"})
```

### Python
Located in `/python`.
```python
from microservice_toolbox.config.loader import AppConfig

ac = AppConfig("standalone", ["my_flag"])
```

### Rust
Located in `/rust`.
```rust
use rust::config::loader::AppConfig;

let ac = AppConfig::load("standalone");
```

## Security Best Practices
Services using this toolbox should NOT publish internal ports in `docker-compose.yaml`. The toolbox handles inter-service discovery via the private Docker network name by default.
