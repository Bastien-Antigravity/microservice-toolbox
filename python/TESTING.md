# Testing: Python Microservice Toolbox

The Python test suite ensures 1:1 behavioral parity with the Go reference engine, focusing on FFI stability and serialization consistency.

## Prerequisites
The Go bridge library must be discoverable (via `LD_LIBRARY_PATH` or `DYLD_LIBRARY_PATH` if not in standard paths).

## Running Tests
Execute from the `python/` root directory:

```bash
cd python
pytest
```

## Zero Warning Standard
The Python implementation is strictly audited for **Zero Warnings**. 
- **UTC Time**: We use timezone-aware `datetime.now(datetime.UTC)` to avoid deprecation noise from naive `utcnow()` calls.

## Key Test Areas

### 1. FFI & Mirroring
- **`test_mirror_integrity`**: Confirms the in-memory dictionary is correctly populated from the Go bridge.
- **`test_decrypt_secret`**: Ensures transparent error passing for RSA decryption failures.

### 2. Configuration (`Local`)
- **`test_unmarshal_local`**: Verifies mapping of the `local:` YAML section to `dataclass` instances.
- **`test_get_local`**: Ensures dot-notation lookups (e.g., `db.host`) work as expected.

### 3. Business Models
- **`test_business_models.py`**: Validates that Python `dataclasses` produce the exact `snake_case` JSON fields expected by Go and Rust.

### 4. Connection Management
- **`test_conn_manager.py`**: Verifies resilient TCP wrappers and automated reconnection logic.
