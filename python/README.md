# Microservice Toolbox - Python Package

The Python implementation of the `microservice-toolbox` provides a lightweight, type-hinted foundation for building resilient microservices. It bridges to the Go reference implementation via FFI to ensure 100% security and logic alignment.

## Installation

Install from the local directory (usually as a git submodule):

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

# On-Demand Decryption (RSA decryption executed via Go core)
pwd = cfg.decrypt_secret("ENC(...)")
```

### 2. Connection Manager (`conn_manager`)
Provides a resilient TCP wrapper around `safesocket` with multiplicative backoff and randomized jitter.

```python
from microservice_toolbox.conn_manager import new_network_manager

nm = new_network_manager(max_retries=5)

# Non-blocking connection: returns immediate wrapper, connects in background
mc = nm.connect_non_blocking("127.0.0.1", "8080", "1.2.3.4", "raw")

# ManagedConnection handles reconnection during write failures automatically
mc.write(b"hello world")
```

### 3. Business Models
Standardized data structures with built-in `snake_case` serialization.

```python
from microservice_toolbox.business.models import MarketEvent, MarketEventType

event = MarketEvent(
    event_id="evt-123",
    symbol="BTC/USDT",
    exchange="BINANCE",
    timestamp=1621234567000,
    type=MarketEventType.TRADE,
    payload=b"..."
)

from microservice_toolbox.business.helpers import serialize

# Ready for cross-language exchange
json_bytes = serialize(event)
```

### 4. Declarative `ServiceSpec` & Exchange Contracts (`spec` & `contracts`)
Authoritative OpenMFE registration (`publish_with_lifecycle`) and live contract introspection (`extract_fastapi_operations`, `extract_proto_operations`, `build_contracts_envelope`).

```python
from microservice_toolbox.contracts import ExchangeContract, build_contracts_envelope, extract_fastapi_operations
from microservice_toolbox.spec import ServiceSpec, publish_with_lifecycle

contracts = [ExchangeContract(id="rest", type="HTTP/1.1 REST", operations=extract_fastapi_operations(app))]
envelope = build_contracts_envelope("my_service", cfg.get_version(), "live FastAPI routes", contracts)
```

## Architecture: The FFI Bridge
To prevent logic drift, the Python SDK does not implement its own configuration resolution or RSA decryption. Instead, it uses `ctypes` to load `libdistconf` (Go). At startup, a **Full Sync** is performed, mirroring the entire Go configuration state into a Python dictionary for sub-millisecond lookups.

## Development & Testing

```bash
# Run tests
cd python && pytest tests

# Run lint checks
ruff check .
```
