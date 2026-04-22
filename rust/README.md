# Microservice Toolbox - Rust Crate

The Rust implementation of the `microservice-toolbox` provides a high-performance, asynchronous foundation using `tokio` and `serde` for building resilient microservices in the Bastien-Antigravity ecosystem.

## Installation

Add the toolbox as a path dependency in your `Cargo.toml`:

```toml
[dependencies]
microservice-toolbox = { path = "../microservice-toolbox/rust" }
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
```

### 2. Connection Manager (`conn_manager`)
Built on `tokio::net::TcpStream`, providing randomized jitter and backoff for network resilience.

```rust
use microservice_toolbox::conn_manager::new_network_manager;
use std::sync::Arc;

// Define a unified hook for error tracking and recovery logic
let on_error = Arc::new(|attempt, err, source, msg| {
    eprintln!("[{}] Error in {}: {} ({:?})", attempt, source, msg, err);
});

let nm = new_network_manager(5, 200, 5000, 2000, 2.0, 0.1);

// Establish a self-healing connection
let mc = nm.connect_blocking("127.0.0.1".to_string(), "8080".to_string()).await;

// The current connection is wrapped in an Arc<Mutex> for safe shared access
let mut stream = mc.current_conn.lock().await;
```

### 3. Serializers (`serializers`)
Provides a consistent `Serializer` trait for JSON and **MsgPack** (`rmp-serde`) formats.

```rust
use microservice_toolbox::serializers::{Serializer, JsonSerializer};

let ser = JsonSerializer;
let bytes = ser.marshal(&my_struct)?;
```

## Advanced Features

## Architecture & Design Decisions

### Polyglot API Parity
A core design goal of the `microservice-toolbox` is to provide a near-identical developer experience across Go, Python, and Rust. 

- **Constructor Signatures**: You may notice that `NetworkManager::new_with_all` exceeds the common Rust limit of 7 arguments. This is an intentional choice to maintain 1:1 parity with the Go and Python implementations.
- **Transparency**: We prioritize explicit configuration and cross-language consistency over the introduction of language-specific configuration objects that would diverge the API surface.

### Docker Guard
The Rust implementation automatically detects `/.dockerenv` or the `DOCKER_ENV` environment variable. When active, it ignores manual CLI network overrides to prevent breaking automated inter-service resolution.

## Testing

Run the crate's test suite:

```bash
cargo test
```
