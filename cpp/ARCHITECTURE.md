# Architecture: C++ Microservice Toolbox

The C++ implementation is designed for maximum performance in latency-sensitive environments.

## 1. Full FFI Bridge Sync
To avoid the overhead of crossing the C++/Go bridge for every configuration lookup, the `AppConfig` class implements a **Full Sync** pattern:
- **Initialization**: Upon startup, it calls `GetFullConfig()` from the Go bridge.
- **Mirroring**: The resulting JSON is parsed using the header-only `nlohmann/json` library and stored in an internal `data_` object.
- **Lookups**: `GetListenAddr` and `GetLocal` read directly from this in-memory mirror.

## 2. Decryption Delegation
While lookups are mirrored, **Decryption** is always delegated back to the Go core. This ensures that the private RSA keys only ever reside in the Go engine's memory space, providing a single, hardened security boundary.

## 3. Hierarchy of Truth
- **CLI Flags**: Managed via the Go engine (if passed through) or system-level overrides.
- **Local Overrides**: The `LoadLocalOverrides()` method manually parses the `private:` section of local YAML files to ensure engine decoupling for service-specific settings.

## 4. Fallback Logic
If the In-memory mirror fails to initialize or contains incomplete data for a specific capability, the toolbox automatically falls back to a direct FFI call to the Go engine as a failsafe.
