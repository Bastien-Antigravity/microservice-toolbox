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
- **Lifecycle (`lifecycle`)**: Utilities and standardized contexts/hooks for proper graceful shutdown of services and inter-thread signaling.
- **Serialization (`serializers`)**: Abstractions for binary messaging integrations, primarily geared toward Cap'n Proto.

## 3. Structural Design

The repository is modularized strictly by target languages:
- `/go`: Reference implementation. Go source of truth.
- `/rust`: Implementation mapping natively to Cargo and standard crates.
- `/python`: Implementation utilizing native type hints and standard packages.

## 4. Usage Rules

This module sits below the `universal-logger` and above native generic capabilities. It should remain stateless and strictly focused on utilities, leaving business logic processing fully decoupled.
