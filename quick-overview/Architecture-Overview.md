---
tags:
- '#ai/ignore'
- '#domain/architecture'
- '#zone/3-fleet'
---

# 🏗️ Architecture Overview

## Executive Summary
The `microservice-toolbox` is a unified, polyglot infrastructure library designed to provide common operational patterns and shared abstractions for the Bastien-Antigravity microservices ecosystem. It ensures a standardized developer experience and consistent orchestration across five primary languages:

- **Go**: The reference implementation and core execution engine.
- **Python**: FFI/ctypes-based wrapper.
- **Rust**: Native type-safe client with serde mapping.
- **C++**: High-speed FFI wrapper utilizing `nlohmann/json`.
- **VBA**: COM-compatible integration for Excel/Access.

## Global System Architecture

```mermaid
graph TD
    subgraph Core Reference (Go)
        GoCore[Go Core Library]
        ConfLoader[Config Loader]
        RSAEngine[RSA Decryption Engine]
        ConnMgr[Connection Manager]
    end

    subgraph Cross-Language FFI Bridging
        PythonSDK[Python SDK] -- ctypes --> GoCore
        RustSDK[Rust SDK] -- cargo/linkage --> GoCore
        CPPSDK[C++ SDK] -- static/dynamic bind --> GoCore
        VBASDK[VBA Module] -- DLL import --> GoCore
    end

    subgraph Data Standards
        CapnP[Cap'n Proto Schemas] --> GoCore
        CapnP --> PythonSDK
        CapnP --> RustSDK
    end
```

## Core Component Pillars
The toolbox consolidates foundational utilities into five critical pillars:

1.  **Configuration (`config`)**: Implements the "Hierarchy of Truth" and the `local:` private namespace.
2.  **Secret Management**: Standardized on-demand RSA decryption engine; secrets remain encrypted as `ENC(...)` in memory.
3.  **Connectivity**: Networking primitives for service lookups, IP resolution, and gRPC server builders.
4.  **Connection Manager (`conn_manager`)**: Resilient TCP connection wrapper with multiplicative backoff and randomized jitter.
5.  **Serialization (`serializers`)**: Cross-language abstractions for JSON and MessagePack round-trips.

## Repository Anatomy
The repository follows a clean, standardized modular design:

```text
microservice-toolbox/
├── go/                   # Go Reference Implementation
│   ├── pkg/
│   │   ├── business/     # MarketEvent, OHLCV, Signal models
│   │   ├── config/       # Hierarchy of Truth loader & overrides
│   │   ├── conn_manager/ # Reconnection loops with jitter & backoff
│   │   ├── connectivity/ # Loopback and Docker address resolvers
│   │   ├── lifecycle/    # Startup & LIFO cleanups
│   │   ├── network/      # gRPC server builders & guards
│   │   ├── serializers/  # JSON and MessagePack handlers
│   │   └── utils/        # UTCTime logger & TUI modules
├── python/               # Python SDK wrapper
├── rust/                 # Type-safe Rust SDK
├── cpp/                  # High-performance C++ header wrapper
├── vba/                  # COM-compatible Excel modules
├── schemas/              # Unified Cap'n Proto definitions
└── integration/          # Multi-language matrix verification suite
```

## Language Bridging Strategy
To prevent logic drift and ensure security alignment, non-Go implementations interact with the Go reference implementation via a high-performance **CGO Bridge** (`libdistconf`).

- **FFI Memory Mirroring (Full Sync)**: To eliminate FFI latency, Python, Rust, and C++ implement a "Full Sync" pattern where the entire Go-managed configuration is mirrored locally in memory at startup.
- **Single Cryptographic Boundary**: Complex logic like RSA decryption remains centralized in the Go core.
- **Container Isolation (Docker Guard)**: Ensures that CLI network overrides are securely ignored inside containerized environments to preserve orchestrated internal service discovery (DNS).
- **Mirroring Mandate**: New features added to the Go (Reference) implementation must be ported to other languages in the same cycle to maintain parity.
