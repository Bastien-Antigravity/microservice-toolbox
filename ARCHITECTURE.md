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

- **Polyglot Uniformity**: Provides equivalent APIs in Go, Rust, and Python, ensuring a standard developer experience regardless of language. Go serves as the reference implementation, and all other languages trace its API behaviors.
- **Bootstrapping Foundation**: Central point for application startup, CLI argument parsing, configuration synchronization via `distributed-config`, and environment variable expansion.
- **Container Isolation**: Features "Docker Guard," ensuring that CLI network definitions are securely ignored inside containerized environments to preserve orchestrated internal service discovery (DNS).

## 2. Core Components

- **Configuration (`config`)**: Reads global standalone configurations using `LoadConfig(profile)` and adapts to overrides securely.
- **Connectivity (`connectivity` / `network`)**: Networking primitives for service lookups, IP resolution, and gRPC server builder patterns.
- **Connection Manager (`conn_manager`)**: Resilient TCP connection wrapper with multiplicative backoff, randomized jitter, and transparent reconnection on write failures. It formalizes three **Connection Modes**: `Blocking` (finite retries), `Non-Blocking` (background reconnection), and `Indefinite` (retry forever, blocking boot). To simplify usage, it provides **Strategy Presets** (`Critical`, `Standard`, `Performance`) that align the manager's internal timing and retry logic with the architectural intent of the service (e.g., Audit logs vs. telemetry).
- **Lifecycle (`lifecycle`)** *(Go only)*: OS signal handling (`SIGINT`, `SIGTERM`) and graceful shutdown orchestration for sub-goroutines. Python and Rust equivalents are planned (see `TODO.md`).
- **Serialization (`serializers`)**: Cross-language serialization abstractions with an identical `marshal`/`unmarshal` API surface. Provides `JSONSerializer` (human-readable payloads) and `BinSerializer` (msgpack, for high-performance binary encoding). Compatible across all three languages.
- **Secret Management (v1.1.9+)**: Standardized **on-demand** RSA decryption engine. Secrets are stored as `ENC(...)` and decrypted via explicit helpers to minimize plaintext exposure. Supports a standardized search chain and the `--key` CLI override across all three languages.

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
