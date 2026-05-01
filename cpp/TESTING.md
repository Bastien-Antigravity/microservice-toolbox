# Testing: C++ Microservice Toolbox

The C++ test suite verifies the mirroring integrity and the FFI bridge stability.

## Compilation
To compile the parity tests on macOS:
```bash
clang++ -std=c++14 tests/test_config.cpp -I./include ../../distributed-config/distconf/libdistconf/libdistconf.dylib -o test_config
```

## Running Tests
Ensure the dylib path is correctly handled (on macOS, you may need to use `install_name_tool` or `DYLD_LIBRARY_PATH`):
```bash
DYLD_LIBRARY_PATH=../../distributed-config/distconf/libdistconf ./test_config
```

## Key Test Cases
- **`test_address_resolution`**: Verifies that capability addresses are correctly parsed and retrieved.
- **`test_mirror_integrity`**: Confirms the `nlohmann/json` mirror is correctly populated from the Go bridge.
- **`test_get_local`**: Validates the extraction of service-specific settings.
- **`test_decrypt_secret_logic`**: Ensures the `ENC(...)` block detection matches the ecosystem standard.
