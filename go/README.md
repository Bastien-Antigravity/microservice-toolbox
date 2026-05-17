# Microservice Toolbox - Go Module (Reference Implementation)

The Go implementation of the `microservice-toolbox` is the foundational library and core engine for the entire Bastien-Antigravity ecosystem. It provides the reference logic for configuration resolution, RSA decryption, and resilient networking.

## Installation

```bash
go get github.com/Bastien-Antigravity/microservice-toolbox/go
```

## Core Pillars

### 1. Configuration (`pkg/config`)
Implements the "Hierarchy of Truth" and the autoritative Go-bridge for non-Go SDKs.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

// Loads standalone.yaml and applies layered priority
cfg := config.LoadConfig("standalone")

// Decrypt secrets using the centralized RSA engine
secret, _ := cfg.DecryptSecret("ENC(...)")
```

### 2. Connection Manager (`pkg/conn_manager`)
High-level TCP orchestration with multiplicative backoff and jitter.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/conn_manager"

nm := conn_manager.NewStandardStrategy(nil)

// Self-healing connection
conn := nm.ConnectBlocking(&ip, &port, &publicIP, "raw")
```

### 3. Business Models (`pkg/business`)
Standardized Market Data and Signal models.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/business"

sig := business.Signal{
    Symbol: "BTC/USDT",
    Type: business.SignalBuy,
}
```

## Architecture: The Reference Engine
The Go module serves as the **Core Execution Engine**. All non-Go implementations (Python, Rust, C++, VBA) bridge to this library (via `libdistconf`) to perform sensitive operations like RSA decryption, ensuring absolute logic synchronization and zero security drift across the fleet.

## Testing
Run the comprehensive Go test suite:
```bash
cd go && go test -v ./pkg/...
```
