# Microservice Toolbox - C++ Module

A high-performance C++14 wrapper for the Bastien-Antigravity configuration ecosystem.

## Features
- **In-memory Mirroring**: Full state sync from Go bridge for low-latency lookups.
- **Hardened Decryption**: Automatic handling of `ENC(...)` blocks.
- **Polyglot Parity**: Matches the Go, Python, and Rust interface exactly.

## Usage

```cpp
#include "microservice_toolbox/config/AppConfig.hpp"

using namespace microservice_toolbox::config;

// Initialize
auto ac = LoadConfig("standalone");

// Access configuration
std::string addr = ac->GetListenAddr("my-service");

// Access local configuration
std::string apiKey = ac->GetLocal("local_setting");
```

## Build Requirements
- C++14 compatible compiler (Clang/GCC).
- `libdistconf` bridge library.
- `nlohmann/json` (included as header-only).
