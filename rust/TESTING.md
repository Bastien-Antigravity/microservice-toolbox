# Testing: Rust Microservice Toolbox

The Rust test suite is integrated into the crate and uses standard `cargo test` infrastructure.

## Prerequisites
Ensure the Go bridge library is compiled and available in the library search path:
- Linux: `libdistconf.so`
- macOS: `libdistconf.dylib`

## Running Tests

### Standard Tests
```bash
cargo test
```

### With Logging
To see internal toolbox logs during test execution:
```bash
RUST_LOG=info cargo test -- --nocapture
```

## Key Test Cases
- **`test_unmarshal_local`**: Verifies that the `private:` YAML section correctly maps to typed Rust structs using `serde`.
- **`test_get_local`**: Ensures local configuration values are correctly extracted.
- **`test_cli_override_targets_single_capability`**: Validates the "Hierarchy of Truth" logic for CLI flags.
- **`test_decrypt_plaintext_passthrough`**: Verifies the hardened decryption logic for `ENC(...)` blocks.
