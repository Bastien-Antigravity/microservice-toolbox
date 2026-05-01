# Microservice Toolbox - Python Package

The Python implementation of the `microservice-toolbox` provides a lightweight, type-hinted foundation for building resilient microservices that are fully compatible with the Bastien-Antigravity Go and Rust ecosystem.

## Installation

As this is a core infrastructure library, it is typically included as a git submodule or installed from the local directory:

```bash
pip install ./python
```

## Core Components

### 1. Configuration (`config`)
Implements the "Hierarchy of Truth". A key feature is the `input_args` parameter, which allows decoupling configuration from `sys.argv` for easier testing.

```python
from microservice_toolbox.config import load_config

# Resolves standalone.yaml and handles Docker Guard logic
cfg = load_config("standalone", input_args=["--log_level", "DEBUG"])

# Get capability address
addr = cfg.get_listen_addr("my_service")

# On-Demand Decryption (Harden security by decrypting just-in-time)
pwd = cfg.decrypt_secret(cfg.data["db"]["password"])
```

### 2. Connection Manager (`conn_manager`)
Provides a resilient TCP wrapper with multiplicative backoff and randomized jitter.

```python
from microservice_toolbox.conn_manager import new_network_manager

# on_error receives (attempt, err, source, msg)
def my_handler(attempt, err, source, msg):
    print(f"[{attempt}] Failure in {source}: {msg}")

nm = new_network_manager(max_retries=5, on_error=my_handler)

# Non-blocking connection: returns immediate wrapper, connects in background
mc = nm.connect_non_blocking("127.0.0.1", "8080", "1.2.3.4", "raw")

# ManagedConnection handles reconnection during write failures automatically
mc.write(b"hello world")
```

### 3. Serializers (`serializers`)
Provides consistent serialization signatures for cross-language data exchange.

```python
from microservice_toolbox.serializers import BinSerializer, JSONSerializer

# All providers share the .marshal() and .unmarshal() API
ser = BinSerializer() # Uses MsgPack for high-performance binary exchange
payload = ser.marshal({"key": "value"})
```

## Development & Testing

The Python module uses `pytest` for testing and `ruff` for linting.

```bash
# Run tests
pytest python/tests

# Run lint checks
ruff check python
```
