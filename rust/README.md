# Microservice Toolbox - Rust Crate

The Rust implementation of the `microservice-toolbox` provides a high-performance, asynchronous foundation using `tokio` and `serde`. It follows the **Mirroring Mandate**, bridging to the Go core for configuration resolution and security.

## Installation

Add the toolbox as a path dependency in your `Cargo.toml`:

```toml
[dependencies]
microservice_toolbox = { path = "../microservice-toolbox/rust" }
```

## Core Components

### 1. Configuration (`config`)
Utilizes `serde_yml` and `clap` to implement the "Hierarchy of Truth".

```rust
use microservice_toolbox::config::load_config;

// Loads standalone.yaml and applies CLI overrides with Docker Guard protection
let cfg = load_config("standalone")?;

// Access capability resolution
let addr = cfg.get_listen_addr("my-service")?;

// Decrypt secrets (RSA decryption executed via Go core)
let secret = cfg.decrypt_secret("ENC(...)")?;
```

### 2. Connection Manager (`conn_manager`)
Built on `tokio::net::TcpStream`, providing randomized jitter and backoff for network resilience.

```rust
use microservice_toolbox::conn_manager::new_network_manager;

let nm = new_network_manager(5, 200, 5000, 2000, 2.0, 0.1);

// Establish a self-healing connection
let mc = nm.connect_blocking("127.0.0.1".to_string(), "8080".to_string()).await;
```

### 3. Business Models
Type-safe data structures with `serde` support for `snake_case` JSON and MsgPack.

```rust
use microservice_toolbox::business::models::{Signal, SignalType};

let sig = Signal {
    source: "strat-1".into(),
    symbol: "BTC/USDT".into(),
    timestamp: 1621234567000,
    signal_type: SignalType::Buy,
    strength: 0.95,
    price: 50000.0,
    metadata: "".into(),
};
```

## Architecture & FFI Safety
The Rust SDK interacts with the Go reference implementation via a high-performance C-linkage bridge. To ensure safety and performance:
- **In-Memory Mirroring**: Full config state is synced at startup, allowing lock-free reads.
- **Thread Safety**: All configuration and networking structures implement `Send + Sync`.
- **Decryption Bound**: RSA logic is centralized in the Go core to maintain a single cryptographic boundary.

## Testing

```bash
cd rust && cargo test
```
