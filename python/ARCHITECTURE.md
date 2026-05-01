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

## 4. Local Configuration (`Local`)
- The `unmarshal_local(target)` method allows mapping the `private:` YAML section to a `dataclass` or any Python class instance.
