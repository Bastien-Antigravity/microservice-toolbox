---
microservice: microservice-toolbox
type: documentation
status: active
tags:
- '#service/microservice-toolbox'
- '#type/documentation'
- '#state/active'
- '#zone/3-fleet'
---

# Microservice Toolbox - Go Module (Reference Implementation)

The Go implementation of the `microservice-toolbox` is the foundational library and core engine for the entire Bastien-Antigravity ecosystem. It provides the reference logic for configuration resolution, RSA decryption, and resilient networking.

## Installation

```bash
go get github.com/Bastien-Antigravity/microservice-toolbox/go
```

## Core Pillars

### 1. Configuration (`pkg/config`)
Implements the "Hierarchy of Truth" and the authoritative Go-bridge for non-Go SDKs.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

// Loads standalone.yaml and applies layered priority
cfg, err := config.LoadConfig("standalone")
if err != nil {
    log.Fatalf("failed to load config: %v", err)
}

// Decrypt secrets using the centralized RSA engine and resolve version via AppConfig
ver := cfg.GetVersion()
secret, _ := cfg.DecryptSecret("ENC(...)")
```

### 2. Connection Manager (`pkg/conn_manager`)
High-level TCP orchestration with multiplicative backoff, jitter, lock-free atomic `Endpoint` pointers, and live `AppConfig` capability resolution.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/conn_manager"

nm := conn_manager.NewNetworkManager(cfg, log)

// Self-healing connection resolved directly from AppConfig (LiveConfig + Capabilities)
conn, err := nm.ConnectCapability("log_server", "tcp-hello:my-service")
```

### 3. Business Models (`pkg/business`)
Standardized Market Data and Signal models.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/business"

sig := business.Signal{
    Symbol: "BTC/USDT",
    Type:   business.SignalBuy,
}
```

### 4. Messaging Connector (`pkg/messaging`)
Unified NATS configuration models and connector factories.

```go
import (
    "time"
    "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
    "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/messaging"
)

// Configure connection parameters
cfg := &messaging.NatsConfig{
    Servers:        []string{"nats://localhost:4222"},
    ClientID:       "my-service",
    ConnectTimeout: 2 * time.Second,
}

// Establish a connection pre-wired with standard retry and logging behavior
nc, err := messaging.Connect(cfg, &logger.FmtLogger{})
```

### 5. Declarative `ServiceSpec` & Exchange Contracts (`pkg/spec`)
Authoritative OpenMFE registration (`PublishWithLifecycle`, `BuildSpecFromConfig`) and runtime Exchange Contract helpers (`ExchangeContract`, `ContractPeer`, `ContractOperation`, `ContractsEnvelope`, `NewContractsEnvelope`, `DisplayAddress`, `ResolveContractPort`, `ExtractProtoTextOperations`, `ExtractCapnpOperations`, `RenderProtoIDL`). `BuildSpecFromConfig` / `PublishWithLifecycle` automatically populates `URL`, `%s` port placeholders in `Framing`, `DataStructure` (`version` via `cfg.GetVersion()`, `capability`, `ports`, `node`), `NavRoute`, `Canvas`, and `Health` from `AppConfig`.

```go
contracts := []spec.ExchangeContract{{
    ID: "grpc", Type: "gRPC / Protobuf", TabLabel: "gRPC Protobuf",
    Address: spec.DisplayAddress(grpcAddr), Port: spec.ResolveContractPort(grpcAddr),
    Operations: spec.ExtractProtoTextOperations(embeddedProto),
    SchemaFormat: "proto3", Schema: embeddedProto,
}}
_ = spec.PublishWithLifecycle(cfg, log, lm, "my_service", spec.ServiceSpec{
    Name: "My Service", Tag: "my-service-mfe", Contracts: contracts,
    Layer: "L2", Category: "Domain Services", Description: "...",
    DocLink: "obsidian-brain/06-Microservices/my-service.md",
    Protocol: "gRPC", Framing: "Port %s gRPC",
})
env := spec.NewContractsEnvelope("my_service", cfg.GetVersion(), "live contracts", contracts)
```

### 6. WireTap, Lifecycle, Connectivity & Notifications
- **WireTap (`pkg/wiretap`)**: Auto-initialized by `bootstrap.BootstrapService` (`ConfigureFromConfig`, `SetEnabled`/`IsEnabled`, `Snapshot`) with automatic hooks on `safe-socket`, `teleremote`, `notification`, `network`, and `messaging`.
- **Lifecycle (`pkg/lifecycle`)**: LIFO shutdown cleanup (`NewManagerWithLogger`, `Register`, `Wait`).
- **Connectivity (`pkg/connectivity`)**: Config-verbatim `Resolver` (`ResolveBindAddr`, `ResolveFullBindAddr`) failing fast on empty host/port.
- **Notifications (`pkg/notification`)**: Direct one-way multi-channel alerting client (`NewClient(cfg, log)`).

## Architecture: The Reference Engine
The Go module serves as the **Core Execution Engine**. All non-Go implementations (Python, Rust, C++, VBA) bridge to this library (via `libdistconf`) to perform sensitive operations like RSA decryption, ensuring absolute logic synchronization and zero security drift across the fleet.

## Testing
Run the comprehensive Go test suite:
```bash
go test -v ./go/...
```

