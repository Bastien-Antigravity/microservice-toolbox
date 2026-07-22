# Microservice Toolbox - Logger Client

The `microservice_toolbox.logger` module provides a high-performance Python client for the unified ecosystem logging server and configuration bridge. It wraps the compiled Go core library (`libunilog`) via `ctypes` FFI to allow seamless logging and real-time distributed configuration updates.

---

## Key Features

1. **Standard & Domain-Specific Logging**: Supports traditional severity levels (`DEBUG` to `CRITICAL`) along with specialized business domains (`LOGON`, `TRADE`, `SCHEDULE`, `REPORT`, etc.).
2. **Metadata Injection**: Allows dynamic tag injection (`add_metadata`) onto outgoing logs.
3. **Live Config Bridging**: Connects to the distributed configuration daemon (`DistConf`) to fetch or set configuration values with Zero-Leak memory safety.
4. **Subscription Listeners**: Supports both synchronous callbacks and asynchronous iterators (`async for`) to handle live configuration update notifications dynamically.

---

## Installation & Discovery

The logger automatically resolves the path to the compiled `libunilog` shared object (`.so` / `.dylib` / `.dll`) via:
1. The `LIBUNILOG_PATH` or `LIBDISTCONF_PATH` environment variables.
2. Common workspace and system search paths.

Ensure that the Go core library is built:
```bash
cd universal-logger
make core
```

---

## Usage Guide

### 1. Basic Initialization & Logging

```python
from microservice_toolbox.logger import UniLog, LogLevel

# Initialize the client session
logger = UniLog(
    app_name="my-microservice",
    config_profile="standalone",  # standalone / clustered
    logger_profile="standard",    # standard / fallback
    log_level="info"
)

# Standard logging
logger.info("Service started successfully.")
logger.warning("Resource utilization approaching threshold.")

# Domain-specific logging
logger.trade("Order filled: BUY 10 AAPL @ 185.50")
logger.schedule("Executing cron job: nightly_cleanup")
```

### 2. High-Performance Asynchronous Logging
Use the non-blocking async variants in asyncio-based applications to avoid blocking the main event loop:

```python
await logger.async_info("Processing inbound request...")
await logger.async_error("Failed to connect to database.")
```

### 3. Dynamic Configuration Access & Synchronization
The UniLog instance acts as a direct bridge to the Go configuration registry.

```python
# Retrieve config properties dynamically
db_host = logger.get_config("database", "host", default="127.0.0.1")

# Update config properties dynamically
logger.set_config("database", "port", "5432")
```

### 4. Listening for Config Updates

#### Synchronous Callbacks
```python
def on_update(config_data: dict):
    print("Received live configuration update:", config_data)

# Register the callback
logger.on_config_update(callback=on_update)
```

#### Asynchronous Iterators (`async for`)
```python
# Start an async configuration update loop
async def watch_config_changes(logger: UniLog):
    async for updated_config in logger.on_config_update():
        print("Async update notification:", updated_config)
```

### 5. Cleaning Up Resources
When shutting down, explicitly release the FFI handle to prevent memory leaks:
```python
logger.close()
```
Or use the context manager:
```python
with UniLog(app_name="temp-service") as logger:
    logger.info("Executing...")
```
