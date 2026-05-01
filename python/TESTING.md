# Testing: Python Microservice Toolbox

The Python test suite uses `pytest` and verifies the FFI bridge connectivity and the mirroring integrity.

## Prerequisites
Ensure the Go bridge library is compiled and available in the search path:
- Linux: `libdistconf.so`
- macOS: `libdistconf.dylib`

## Running Tests

### Standard Tests
```bash
export PYTHONPATH=$PYTHONPATH:.
pytest tests/test_config.py
```

### Coverage
```bash
pytest --cov=microservice_toolbox tests/
```

## Key Test Cases
- **`test_unmarshal_local`**: Verifies mapping of private YAML sections to Python classes.
- **`test_get_local`**: Ensures local configuration values are correctly extracted.
- **`test_cli_overrides`**: Validates that Python's `argparse` integration matches Go's `pflag` behavior.
- **`test_mirror_integrity`**: Confirms the in-memory mirror is correctly populated from the FFI bridge.
