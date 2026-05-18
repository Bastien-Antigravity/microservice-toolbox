# Testing: Rust Microservice Toolbox

The Rust test suite uses standard `cargo test` infrastructure and ensures memory safety, thread safety, and polyglot parity.

## Prerequisites
The Go bridge library (`libdistconf`) must be compiled and discoverable.

## Running Tests

### Standard Execution
```bash
cd rust && cargo test
```

### With Detailed Logging
To see internal toolbox logs during test execution:
```bash
RUST_LOG=info cargo test -- --nocapture
```

## Key Test Areas

### 1. Configuration & Parity
- **`test_unmarshal_local`**: Verifies that the `local:` YAML section correctly maps to typed Rust structs using `serde`.
- **`test_cli_override_targets_single_capability`**: Validates the "Hierarchy of Truth" logic for CLI flags.
- **`test_decrypt_plaintext_passthrough`**: Verifies the hardened decryption logic for `ENC(...)` blocks.

### 2. Business Models
- **`test_business_models.rs`**: Validates that Rust structs produce the exact `snake_case` JSON fields expected by Go and Python.

### 3. Connection Management (Async)
- **`test_unified_connect`**: Verifies resilient connection establishment using `tokio` async tasks.
- **`test_on_error_unified_hook`**: Validates the error tracking and reporting logic.

### 4. Lifecycle
- **`test_lifecycle_lifo_order`**: Confirms that cleanup handlers are executed in LIFO (Last-In-First-Out) order.
