# Architecture: Rust Microservice Toolbox

The Rust implementation provides a safe, high-performance interface to the Go configuration engine using `extern "C"` blocks.

## 1. FFI Safety
The `src/config/ffi.rs` module contains the raw FFI bindings. We use a safety-first approach:
- C-strings are converted to Rust `String` safely with ownership management.
- The `libloading` crate is used to dynamically bind to the Go bridge at runtime.

## 2. In-Memory Mirroring (Full Sync)
Similar to Python, Rust performs a **Full Sync** on initialization:
- Fetches the entire config JSON via `dist_conf_get_full_config`.
- Parses it into a `serde_yml::Value` (mapping) once.
- All subsequent `get_local` or `get_listen_addr` calls read from this `Value`, avoiding unsafe FFI calls during runtime.

## 3. Hierarchy of Truth
- **CLI Flags**: Rust uses `clap` to parse flags like `--key` to maintain parity with Go's CLI interface.
- **Environment Variables**: Managed via `std::env`.
- **Local Mirror**: The `AppConfig` struct owns the mirrored configuration state.

## 4. Type-Safe Local Configuration (`Local`) & Standard SDK Parity
- `unmarshal_local<T>()`: Leverages `serde` to deserialize the `local:` YAML section into any Rust struct that implements `Deserialize`.
- **Standard Tools**: `AppConfig::get_version()`, `spec` & `contracts` (`publish_with_lifecycle`, `build_spec_from_config`, IDL extractors), `wiretap`, `notification`, `connectivity::Resolver`, `LifecycleManager`, `business`, and `serializers`.

## 5. Resilient Connection Manager (`conn_manager`)
- **Unified Constructor**: `new_network_manager(app_config, logger)` creates the manager with pointer-based config and logger binding.
- **Lock-Free Atomic Endpoint Pointer Architecture**: Coordinates are stored in `Arc<std::sync::RwLock<Arc<Endpoint>>>` with precomputed `address` (`host:port`). Hot-path reconnection reads from `ep.address` directly without async locks or loose temporary string variables.
- **Direct `AppConfig` Resolution on Reconnect**: Reconnection loops handle severed sockets by evaluating `get_listen_addr(capability)` directly from `AppConfig`. Target coordinate updates swap the `Arc<Endpoint>` pointer atomically without requiring microservice restarts.
