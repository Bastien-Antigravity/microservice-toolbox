# Testing: C++ Microservice Toolbox

The C++ test suite verifies the mirroring integrity, FFI bridge stability, and networking resilience.

## Running Tests
The easiest way to run the full suite is via the provided `Makefile`:

```bash
cd cpp && make test
```

## Key Test Areas

### 1. Configuration Parity (`test_config.cpp`)
- **`test_address_resolution`**: Verifies that capability addresses are correctly parsed and retrieved.
- **`test_mirror_integrity`**: Confirms the `nlohmann/json` mirror is correctly populated from the Go bridge.
- **`test_get_local`**: Validates the extraction of service-specific settings from the `local:` YAML section.
- **`test_decrypt_secret_logic`**: Ensures the `ENC(...)` block detection and transparent error passing matches the ecosystem standard.

### 2. Networking Resilience (Integrated)
- Validates the `ManagedConnection` wrapper's ability to handle simulated disconnects using the policies defined in `NetworkManager`.

### 3. Business Model Compatibility
- Ensures that `Models.hpp` structures serialize to `snake_case` JSON compatible with Go, Python, and Rust.

## Technical Compilation (Manual)
To compile manually on macOS (adjust for Linux/Windows):
```bash
clang++ -std=c++14 tests/test_config.cpp -I./include ../../distributed-config/distconf/libdistconf/libdistconf.dylib -o test_config
DYLD_LIBRARY_PATH=../../distributed-config/distconf/libdistconf ./test_config
```
