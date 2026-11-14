# Testing: C++ Microservice Toolbox

The C++ test suite verifies the mirroring integrity, FFI bridge stability, and networking resilience.

## Running Tests
The easiest way to run the full suite is via the provided `Makefile`:

```bash
cd cpp && make test
```

## Key Test Areas

### 1. Configuration Parity (`test_config.cpp`)
- Verifies `LoadConfig` FFI full sync, `GetListenAddr`/`GetGRPCListenAddr`/`GetRESTAddr`, fail-fast error propagation on missing gRPC capability, `GetLocal`, `DecryptSecret`, environment expansion, and `ValidateUniquePorts`.

### 2. Core Parity Modules (`test_modules.cpp`)
- Validates `Connectivity::Resolver` (config-verbatim fail-fast resolution), `LifecycleManager` LIFO execution, `Business` models + JSON/MsgPack serialization (`JsonSerializer`, `BinSerializer`), `Logger` interface, and lock-free `WireTap` telemetry.

### 3. Notifications & Versioning (`test_notification.cpp`, `test_version.cpp`)
- **`test_notification.cpp`**: Validates fail-fast `NotificationClient::FromConfig`, address validation, dynamic `libnotif` C ABI loading, and close/timeout handling.
- **`test_version.cpp`**: Verifies `VERSION.txt`-only resolution via `GetVersion()`, fail-fast exception when absent, and strict ignoring of runtime env vars.

### 4. ServiceSpec & Exchange Contracts (`test_spec.cpp` & `test_contracts_c.c`)
- **`test_spec.cpp`**: Verifies `ProtocolSpec`, `ExchangeContract`, `ContractsEnvelope`, `ExtractProtoTextOperations`, `ExtractCapnpOperations`, fail-fast validation in `SpecPublisher::BuildSpecFromConfig`/`PublishSync`, and C ABI JSON parsing.
- **`test_contracts_c.c`**: Pure C11 (`-std=c11 -Wall -Wextra -Werror`) suite verifying `MtExchangeContract`, `MtContractsEnvelope`, address/port normalization, UTC ISO-8601 formatting, and RFC 8259 JSON escaping via `mt_contracts_envelope_to_json`.

## Manual Compilation Reference
To compile manually on macOS (C++17):
```bash
g++ -std=c++17 tests/test_config.cpp -I./include -I../../distributed-config/distconf/libdistconf -L../../distributed-config/distconf/libdistconf -ldistconf -Wl,-rpath,../../distributed-config/distconf/libdistconf -o bin/test_config
DYLD_LIBRARY_PATH=../../distributed-config/distconf/libdistconf ./bin/test_config
```
