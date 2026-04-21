# Microservice Toolbox - Go Module

The Go implementation of the `microservice-toolbox` provides a robust foundation for building high-performance, resilient microservices within the Bastien-Antigravity ecosystem.

## Installation

Add the toolbox to your `go.mod`:

```bash
go get github.com/Bastien-Antigravity/microservice-toolbox/go
```

## Core Components

### 1. Configuration (`pkg/config`)
The configuration loader implements the "Hierarchy of Truth" and platform-aware merging.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"

// Loads standalone.yaml, applies overrides, and enables Docker Guard
cfg := config.LoadConfig("standalone")

// Access capabilities
addr := cfg.GetListenAddr("my-service")
```

### 2. Connection Manager (`pkg/conn_manager`)
Handles TCP connections with automated retries, backoff, and background recovery.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/conn_manager"

nm := conn_manager.NewNetworkManager(5, 200, 5000, 2000, 2.0, 0.1)

// Unified error and retry hook
nm.OnError = func(attempt int, err error, source string, msg string) {
    log.Printf("[%d] Error in %s: %v", attempt, source, err)
}

// Blocking connection
conn := nm.ConnectBlocking(&ip, &port, &publicIP, "raw")
defer conn.Close()
```

### 3. Lifecycle (`pkg/lifecycle`)
Manages OS signals and ensures all registered components shut down gracefully.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/lifecycle"

m := lifecycle.NewManager()
m.Register("database", func() error {
    return db.Close()
})

// Blocks until SIGINT/SIGTERM, then executes cleanups
m.Wait()
```

### 4. Serializers (`pkg/serializers`)
Shared abstractions for JSON and high-performance **MsgPack** binary formats.

```go
import "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/serializers"

ser := serializers.NewJSONSerializer() // or serializers.NewBinSerializer()
data, _ := ser.Marshal(myStruct)
```

## Testing

Run the Go test suite:

```bash
go test -v ./pkg/...
```
