# Microservice Toolbox - C++ Module

A high-performance C++14 infrastructure library for the Bastien-Antigravity ecosystem, providing 1:1 behavioral parity with the Go reference implementation.

## Features
- **In-memory Mirroring**: Full state sync from the Go CGO Bridge (`libdistconf`) for sub-millisecond lookups.
- **Hardened Decryption**: Standardized RSA decryption via the Go engine for `ENC(...)` blocks.
- **Resilient Networking**: Automated reconnection with multiplicative backoff and randomized jitter.
- **Business Standards**: Standardized structures for Market Data and Signals with `snake_case` JSON compatibility.

## Core Components

### 1. Configuration (`AppConfig`)
Provides a hardened API for the "Hierarchy of Truth" and dynamic updates.

```cpp
#include "microservice_toolbox/config/AppConfig.hpp"

using namespace microservice_toolbox::config;

// Initialize session (standalone or fleet)
auto ac = LoadConfig("standalone");

// High-level resolution (Docker Guard aware)
std::string addr = ac->GetListenAddr("market-observer");

// Decrypt secrets just-in-time
std::string dbPwd = ac->DecryptSecret("ENC(...)");
```

### 2. Connection Manager (`conn_manager`)
Wraps `SafeSocket` to provide self-healing TCP connections.

```cpp
#include "microservice_toolbox/conn_manager/ManagedConnection.hpp"

using namespace microservice_toolbox::conn_manager;

auto nm = NetworkManager::NewStandard();

// Returns a resilient wrapper that handles reconnects in the background
auto mc = nm->ConnectNonBlocking("127.0.0.1", "9000", "1.2.3.4", "raw");

mc->Send({0x01, 0x02, 0x03});
```

### 3. Business Models
Standardized data structures for cross-repo serialization.

```cpp
#include "microservice_toolbox/business/Models.hpp"

using namespace microservice_toolbox::business;

Signal sig;
sig.symbol = "BTC/USDT";
sig.type = SignalType::Buy;

// Generates snake_case JSON for Go/Python/Rust compatibility
nlohmann::json j = sig.to_json();
```

## Build Requirements
- **C++14** compatible compiler (Clang/GCC).
- **libdistconf**: The Go-based CGO bridge library.
- **nlohmann/json**: Header-only JSON library (included).

## Testing
Run the C++ parity suite:
```bash
make test
```
