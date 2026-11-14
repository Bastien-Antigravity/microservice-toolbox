# Architecture: Python Microservice Toolbox

The Python implementation provides a Pythonic wrapper around the Go configuration engine using `ctypes` FFI.

## 1. FFI Bridge
Python does not re-implement the configuration resolution logic. Instead:
- It loads `libdistconf.so` (Linux) or `libdistconf.dylib` (macOS).
- It creates a Go-managed session.
- All decryption and network resolution is delegated to the Go bridge.

## 2. In-Memory Mirroring (Full Sync)
To minimize FFI overhead, the Python toolbox performs a **Full Sync** on startup:
- It calls `DistConf_GetFullConfig()` to fetch the entire state as JSON.
- It stores this state in a local dictionary (`self.data`).
- All subsequent lookups are resolved in-memory within Python, making it as fast as native Go.

## 3. Hierarchy of Truth
- **CLI Flags**: Python parses `--key` and other flags manually using `argparse` to maintain parity with Go.
- **Environment Variables**: Managed via `os.environ`.
- **Local JSON Mirror**: Used for all high-frequency lookups.

## 4. Local Configuration (`Local`) & Standard SDK Parity
- `unmarshal_local(target)` maps the `local:` YAML section to a Python `dataclass` or class instance.
- **Standard Tools**: `get_version()` (`AppConfig.get_version()`), `init_microservice` (bootstrap + WireTap), `spec` & `contracts` (OpenMFE registration + `ExchangeContract` extractors), `wiretap`, `notification`, `connectivity.Resolver`, `LifecycleManager`, `business`, and `serializers`.

## 5. Resilient Connection Manager (`conn_manager`)
- **Unified Constructor**: `new_network_manager(app_config=..., logger=...)` binds `AppConfig` and logger pointers directly.
- **Lock-Free Atomic Endpoint Pointer Architecture**: Coordinates are encapsulated in an immutable `Endpoint` instance (`ip`, `port`, `public_ip`, `profile`, `address`). Hot-path reads access `self.endpoint.address` directly without temporary local string variables. Reference assignments under the Python GIL guarantee atomic coordinate swaps.
- **Dynamic 3-Try Config Reload**: Reconnection loops handle severed sockets. Every 3 failed attempts, `ManagedConnection` queries `app_config.sync()` and `get_listen_addr(capability)`. Target coordinate changes dynamically re-bind the connection without requiring microservice restarts.
- **Write Recovery**: On broken socket write errors (`send`), the severed socket is closed and cleared, inline reconnection is triggered, and the pending write retries once on the restored connection.
