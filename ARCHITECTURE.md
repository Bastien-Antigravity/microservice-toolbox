---
microservice: microservice-toolbox
type: architecture
status: active
tags:
  - domain/architecture
  - domain/configuration
---

# Architecture Standards: Microservice Toolbox

The `microservice-toolbox` serves as the standardized entry point and underlying framework for all cross-language services in the Bastien-Antigravity ecosystem. It offers shared abstractions and foundational utilities needed to orchestrate microservices effectively.

## 1. Architectural Role

- **Polyglot Uniformity**: Provides equivalent APIs in **Go, Rust, Python, C++, and VBA**, ensuring a standard developer experience regardless of language.
- **FFI Bridge Strategy**: Go serves as the "Reference Implementation" and the core execution engine. All other languages (Python, Rust, C++, VBA) interact with this core via a high-performance **CGO Bridge** (`libdistconf`). This ensures that complex logic like RSA decryption and network resolution remains consistent and centralized.
- **In-Memory Mirroring**: To eliminate FFI latency, Python, Rust, and C++ implement a "Full Sync" pattern where the entire Go-managed configuration is mirrored locally in memory (as JSON or native maps) at startup.
- **Container Isolation**: Features "Docker Guard," ensuring that CLI network definitions are securely ignored inside containerized environments to preserve orchestrated internal service discovery (DNS).

## 2. Core Components

- **Configuration (`config`)**: Implements the "Hierarchy of Truth" and the `Local` (private) configuration namespace.
- **Secret Management**: Standardized **on-demand** RSA decryption engine. Secrets are stored as `ENC(...)` and decrypted via the Go core to minimize plaintext exposure. Supports the `--key` CLI override across all five languages.
- **Connectivity**: Networking primitives for service lookups, IP resolution, and gRPC server builder patterns.
- **Connection Manager (`conn_manager`)**: Resilient TCP connection wrapper with multiplicative backoff and randomized jitter (Go, Python, Rust).
- **Serialization (`serializers`)**: Cross-language serialization abstractions (JSON and Msgpack).

## 3. Technical Deep Dives

### The Hierarchy of Truth (Configuration)
The toolbox enforces a deterministic configuration priority to ensure consistency across environments:
1.  **CLI Flags**: Highest priority. Standard flags like `--host`, `--port`, and `--conf` override everything else.
2.  **Dev Mode Overrides**: In `standalone` or `test` profiles, the local YAML file is re-applied over remote state to allow rapid local iteration.
3.  **Fleet State**: In production profiles, the central Configuration Server remains the authoritative source of truth.
4.  **Base Defaults**: Hardcoded environment defaults.

### The Docker Guard (Networking)
To prevent "brittle" hardcoded networking from breaking automated container orchestration, the toolbox implements a strict Docker Guard:
- **Loopback Translation**: If a service requests a bind to `127.0.0.1` inside a container, the toolbox automatically resolves this to the container's primary network interface IP.
- **Override Suppression**: CLI flags for networking (`--host`, `--port`, etc.) are **strictly ignored** when `/.dockerenv` is detected. This ensures that only the orchestrated container network is used for inter-service communication.
