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

# Resolves standalone.yaml and applies CLI Docker Guard
cfg = load_config("standalone", input_args=["--log_level", "DEBUG"])

# Read version directly from AppConfig (VERSION.txt only, fail-fast)
ver = cfg.get_version()

# Get capability address
addr = cfg.get_listen_addr("my_service")

# On-Demand Decryption (RSA decryption executed via Go core)
pwd = cfg.decrypt_secret("ENC(...)")
```

### 2. Connection Manager (`conn_manager`)
Provides a resilient TCP wrapper around `safesocket` with multiplicative backoff, randomized jitter, lock-free `Endpoint` references, and live `AppConfig` capability resolution.

```python
from microservice_toolbox.conn_manager import new_network_manager

nm = new_network_manager(cfg, logger)

# Resolve capability directly from AppConfig (LiveConfig + Capabilities)
mc = nm.connect_capability("log_server", "tcp-hello:my-service")

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
Authoritative OpenMFE registration (`publish_with_lifecycle`, `build_spec_from_config`) and live contract introspection (`extract_fastapi_operations`, `extract_proto_operations`, `extract_capnp_operations`, `build_contracts_envelope`, `new_contracts_envelope`, `display_address`, `resolve_contract_port`). `publish_with_lifecycle` automatically enriches `url`, `%s` port placeholders in `framing`, `data_structure` (`version` via `cfg.get_version()`, `capability`, `ports`, `node`), `nav_route`, `canvas`, and `health`.

```python
from microservice_toolbox.contracts import ExchangeContract, build_contracts_envelope, extract_fastapi_operations
from microservice_toolbox.spec import ServiceSpec, publish_with_lifecycle

contracts = [ExchangeContract(id="rest", type="HTTP/1.1 REST", operations=extract_fastapi_operations(app))]
envelope = build_contracts_envelope("my_service", cfg.get_version(), "live FastAPI routes", contracts)
```

### 5. WireTap, Notifications, Lifecycle & Connectivity
- **WireTap (`microservice_toolbox.wiretap`)**: Automatically configured by `init_microservice` (`configure_from_config`, `set_enabled`/`is_enabled`, `record_event`, `snapshot`).
- **Notification Client (`microservice_toolbox.notification`)**: `NotificationClient.from_config(cfg, logger)` over `libnotif`.
- **Lifecycle (`microservice_toolbox.lifecycle`)**: LIFO shutdown `LifecycleManager` (`register`, `wait`).
- **Connectivity (`microservice_toolbox.connectivity`)**: Config-verbatim `Resolver` (`resolve_bind_addr`, `resolve_full_bind_addr`).

## Architecture: The FFI Bridge
To prevent logic drift, the Python SDK does not implement its own configuration resolution or RSA decryption. Instead, it uses `ctypes` to load `libdistconf` (Go). At startup, a **Full Sync** is performed, mirroring the entire Go configuration state into a Python dictionary for sub-millisecond lookups.

## Development & Testing

```bash
# Run tests
cd python && pytest tests

# Run lint checks
ruff check .
```
