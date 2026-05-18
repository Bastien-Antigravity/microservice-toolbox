# Architecture: C++ Microservice Toolbox

The C++ implementation is designed for maximum performance in latency-sensitive environments while maintaining full parity with the polyglot ecosystem.

## 1. Full FFI Bridge Sync
To avoid the overhead of crossing the C++/Go bridge for every configuration lookup, the `AppConfig` class implements a **Full Sync** pattern:
- **Initialization**: Upon startup, it calls `GetFullConfig()` from the Go bridge.
- **Mirroring**: The resulting JSON is parsed using the header-only `nlohmann/json` library and stored in an internal `data_` object.
- **Lookups**: `GetListenAddr` and `GetLocal` read directly from this in-memory mirror.

## 2. Core Modules (Parity Expansion)
- **Business**: Standard models (`MarketEvent`, `Trade`, `Signal`) with unified JSON mapping.
- **Connectivity**: `Resolver` for environment-aware address translation (Docker vs Native).
- **Serializers**: High-performance `JsonSerializer`.
- **Lifecycle**: `LifecycleManager` for graceful shutdown via signal handling (SIGINT/SIGTERM) and LIFO cleanup execution.
- **Conn Manager**: `NetworkManager` for managing reconnection policies with backoff and jitter.

## 3. Decryption Delegation
While lookups are mirrored, **Decryption** is always delegated back to the Go core. This ensures that the private RSA keys only ever reside in the Go engine's memory space, providing a single, hardened security boundary.

## 4. Hierarchy of Truth
- **CLI Flags**: Managed via the Go engine (if passed through) or system-level overrides.
- **Local Overrides**: The `LoadLocalOverrides()` method manually parses the `local:` section of local YAML files to ensure engine decoupling for service-specific settings.

## 5. Fallback Logic
If the In-memory mirror fails to initialize or contains incomplete data for a specific capability, the toolbox automatically falls back to a direct FFI call to the Go engine as a failsafe.
