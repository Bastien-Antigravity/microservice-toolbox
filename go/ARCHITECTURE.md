# Architecture: Go Microservice Toolbox

The Go implementation serves as the **Reference Implementation** for the entire polyglot ecosystem. It contains the core logic for the "Hierarchy of Truth" and the Docker Guard resolution.

## 1. Hierarchy of Truth
Configuration is resolved in the following priority:
1.  **CLI Flags**: Highest priority (e.g., `--key path/to/private.pem`).
2.  **Environment Variables**: OS-level overrides (e.g., `BASTIEN_PRIVATE_KEY_PATH`).
3.  **Local YAML**: File-based settings (e.g., `standalone.yaml`).
4.  **Remote/Defaults**: Infrastructure-level settings.

## 2. Docker Guard
A specialized networking layer that detects if a service is running inside a Docker container.
- **Native Mode**: Uses resolved IP addresses as-is.
- **Docker Mode**: Automatically rewrites binding addresses to `0.0.0.0` to ensure connectivity through container port mappings, regardless of what the config says.

## 3. Decryption Engine
Integrates directly with `distributed-config` to handle `ENC(...)` blocks. It uses process-local environment variables to discover the RSA keys, allowing for seamless CLI overrides via the `--key` flag.

## 4. Local Configuration (`Local`)
The `AppConfig` struct includes a `Local` map (parsed from the `local:` YAML section). This section is reserved for service-specific, non-synchronized settings.
- `UnmarshalLocal(target)`: Decodes this section into a user-provided struct.

## 5. Standardized Business Data
The Go implementation defines the canonical business data models in `pkg/business`. This package provides the standardized structure for the fleet:
- **MarketEvent**: A unified envelope for L1/L2 data (Trades, Quotes, OrderBooks).
- **OHLCV**: Canonical bar data for time-series analysis.
- **Signal**: Unified trading strategy signals (Buy/Sell/Exit).

All business services should use these models for inter-service communication to maintain structural integrity across the hierarchy.

## 6. Polyglot Parity & Development Rules
The `microservice-toolbox` is a polyglot foundation. To maintain ecosystem stability, the following rules apply to all contributors:

### 6.1 Mirroring Mandate
Whenever a new feature, model, or helper function is added to the Go (Reference) implementation, it **MUST** be ported to all other supported languages (Python, C++, Rust, VBA) within the same development cycle. No feature is considered "Done" until parity is achieved.

### 6.2 Semantic Consistency
Behavior must be identical across all implementations. If `UnmarshalLocal` in Go returns a specific error for a missing key, the Python and Rust implementations must mimic this behavior exactly.

### 6.3 Naming Conventions
To ensure a consistent developer experience while respecting language idioms, we follow these naming rules:
- **Go**: `PascalCase` for public methods/structs (e.g., `GetListenAddr`).
- **Python/Rust**: `snake_case` (e.g., `get_listen_addr`).
- **C++**: `camelCase` or `PascalCase` (following the project's C++ style).
- **Semantics**: The core word sequence must be identical across all languages. Do not use `fetch_ip` in Python if the Go equivalent is `GetListenAddr`.

### 6.4 Verification
Cross-language compatibility is verified via the `integration/` suite. Any change to the toolbox must pass the polyglot matrix tests to ensure that a value serialized in one language can be reliably deserialized in another.
