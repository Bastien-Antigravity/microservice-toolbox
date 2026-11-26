---
microservice: microservice-toolbox
type: architecture
status: active
language: polyglot
tags:
- '#service/microservice-toolbox'
- '#type/architecture'
- '#state/active'
- '#ai/ignore'
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
The toolbox consolidates shared infrastructure into reusable polyglot modules so microservices never reimplement common plumbing:

1. **Configuration & Bootstrap (`config`, `bootstrap`)**: Implements the "Hierarchy of Truth", `local:` private namespace, CLI Docker Guard, and single-call service initialization.
2. **Versioning (`version` via `AppConfig.GetVersion()`)**: Dedicated `AppConfig` method resolving `VERSION.txt` strictly (fail-fast if absent; zero `"0.0.1"` fallbacks or runtime env overrides).
3. **Secret Management**: Standardized on-demand RSA decryption via `libdistconf`; secrets remain encrypted as `ENC(...)` in memory.
4. **Connectivity & Lifecycle (`connectivity`, `conn_manager`, `lifecycle`, `network`)**: Config-verbatim `Resolver`, infinite-retry `conn_manager`, LIFO `LifecycleManager`, and gRPC server builders.
5. **Declarative Specs, Contracts & WireTap (`spec`, `wiretap`)**: Auto-enriched OpenMFE `ServiceSpec` registration, `ExchangeContract`/IDL extractors (including pure C11 `contracts.h`), and lock-free `WireTap` telemetry.
6. **Direct Alerts, Bot Control & Messaging (`notification`, `teleremote`, `messaging`, `business`, `serializers`)**: Multi-channel `notif-server` client, Telegram menu streams, NATS connectors, canonical domain models, and JSON/MsgPack serializers.

## Repository Anatomy
The repository follows a standardized modular design:

```text
microservice-toolbox/
├── go/pkg/               # Go Reference Implementation
│   ├── bootstrap/        # BootstrapService / BootstrapServiceSafe
│   ├── business/         # MarketEvent, OHLCV, Signal models & helpers
│   ├── config/           # AppConfig (LoadConfig, GetVersion, GetListenAddr...)
│   ├── conn_manager/     # Reconnection loops with jitter & backoff
│   ├── connectivity/     # Config-verbatim address Resolver
│   ├── lifecycle/        # LIFO cleanup Manager & signal trapping
│   ├── messaging/        # Resilient NATS Core / JetStream connector
│   ├── network/          # gRPC server builder & WireTap interceptors
│   ├── notification/     # Direct multi-channel alert client (notif-server)
│   ├── serializers/      # JSON and MessagePack handlers
│   ├── spec/             # ServiceSpec, BuildSpecFromConfig & contracts.go
│   ├── teleremote/       # TeleRemote bi-di gRPC client
│   ├── utils/            # Logger, TUI helpers
│   ├── version/          # Internal VERSION.txt engine backing AppConfig.GetVersion()
│   └── wiretap/          # Lock-free real-time transport telemetry aggregator
├── python/               # Python SDK (incl. contracts.py, spec.py, wiretap.py)
├── rust/                 # Rust SDK (incl. spec.rs, contracts re-export, wiretap)
├── cpp/                  # C++17 header SDK & pure C11 spec/contracts.h
├── vba/                  # COM-compatible Excel modules (AppConfig, NotificationClient)
├── schemas/              # Unified Cap'n Proto definitions
└── integration/          # Multi-language matrix verification suite
```

## Language Bridging Strategy
To prevent logic drift and ensure security alignment, non-Go implementations interact with the Go reference implementation via a high-performance **CGO Bridge** (`libdistconf`).

- **FFI Memory Mirroring (Full Sync)**: To eliminate FFI latency, Python, Rust, and C++ implement a "Full Sync" pattern where the entire Go-managed configuration is mirrored locally in memory at startup.
- **Single Cryptographic Boundary**: Complex logic like RSA decryption remains centralized in the Go core.
- **Container Isolation (Docker Guard)**: Ensures that CLI network overrides are securely ignored inside containerized environments to preserve orchestrated internal service discovery (DNS).
- **Mirroring Mandate**: New features added to the Go (Reference) implementation must be ported to other languages in the same cycle to maintain parity.
