# AI Session State: microservice-toolbox

## 🟢 Current Objective
Enable local configuration loading across all profiles for ecosystem parity.

## 📝 Recent Changes
- **Go Toolbox**: Removed the `isDev` gate in `pkg/config/loader.go`. The local YAML file (and the `local:` section) is now applied as a hard override in ALL profiles, including production and staging.
- **Python Toolbox**: Synchronized `microservice_toolbox/config/loader.py` to remove the `is_dev` gate. Local configuration is now authoritative across the entire fleet.
- **Rust Toolbox**: Updated `src/config/loader.rs` to follow the same "always-apply" rule for local file overrides.
- **Architecture Parity**: Ensured that the "Hierarchy of Truth" consistently respects the local YAML file's `local:` section regardless of the environment.
- **Time Sovereignty (UTC)**: Updated `terminal_ui` implementations in **Go, Python, and Rust** to strictly use UTC timestamps, ensuring cross-platform logging consistency and adhering to the new global mandate.

## 🛠️ Pending Tasks
- [ ] Verify VBA and C++ implementations for strict adherence (preliminary audit shows they already follow the "always-load" rule).
- [ ] Add integration tests for production-mode local config loading.

## 🐛 Local Issues / Bugs
- None identified in this session.

### [SCAN] Role: DocMaintainer & Sentinel | State: Completed Documentation Audit
- **Metadata Hardening**: Applied `#ai/ignore` tags and unified YAML frontmatter across all `quick-overview/` files.
- **Archive Integration**: Merged critical technical details from `_archive/ARCHITECTURE.md` (CGO Bridge, Full Sync pattern) and `_archive/TESTING.md` (testify/assert, Arc/Mutex, tokio) into current documentation.
- **Parity Verification**: Confirmed business model implementation (MarketEvent, OHLCV, Signal) across Go, Python, Rust, and C++. Updated parity matrix in root README.md.
- **Zero-Drift Enforcement**: Ensured `README.md` documentation index points to accurate sub-documentation.

### [SCAN] Role: Sentinel | State: Exposed API Audit Results
- **AppConfig Parity**: 
    - Go, Python, Rust: **100% OK**.
    - C++: **GAPS**. Missing `GetServiceName`, `OnLiveConfUpdate`, `OnRegistryUpdate`, `ShareConfig`.
    - VBA: **Minimalist**. Functional for basic needs, but lacks advanced callbacks.
- **Business Models Parity**:
    - Go, Python, Rust: **100% OK** (verified snake_case JSON mapping).
    - C++: **FAIL**. Missing `Quote`, `OrderBook`, `OrderBookLevel`. 
    - **Drift Alert**: C++ uses `camelCase` for `event_id` and `trade_id`, breaking cross-repo serialization consistency.
- **Connection Manager Parity**:
    - Go, Python, Rust: **100% OK**.
    - C++: **FAIL**. Missing `ManagedConnection` class and orchestration methods (`ConnectBlocking`, etc). Only delay policy exists.

### [SCAN] Role: Sentinel | State: C++ API Alignment Completed
- **Business Models Fix**: Updated `Models.hpp` to use `snake_case` for JSON serialization. Added missing `Quote`, `OrderBook`, and `OrderBookLevel` structures.
- **AppConfig Enhancement**: Added `GetServiceName`, `OnLiveConfUpdate`, `OnRegistryUpdate`, and `ShareConfig` methods to `AppConfig.hpp`.
- **Connectivity Tier**: Implemented `ManagedConnection.hpp` with automated reconnection logic (backoff/jitter). Updated `NetworkManager.hpp` with high-level orchestration methods (`ConnectBlocking`, `ConnectNonBlocking`).
- **Zero-Drift Status**: C++ toolbox now satisfies the **Mirroring Mandate** for core configuration, networking, and business logic tiers.

### [SCAN] Role: Sentinel | State: Technical Debt Cleanup (Python UTC)
- **Warning Resolution**: Replaced deprecated `datetime.utcnow()` with modern timezone-aware `datetime.now(UTC)` in `terminal_ui.py`.
- **Verification**: Verified zero warnings in Python test suite (29 tests passed).

### [SCAN] Role: Sentinel | State: Bridge Hardening & C++ Refactor Completed
- **Go Bridge Enhancement**: Added `ApplyFileOverride` to `libdistconf` CGO bridge and facade. This allows non-Go SDKs to leverage Go-native YAML AST parsing and environment expansion (``).
- **C++ Refactor (Logic Identity)**: Deleted 100+ lines of manual C++ YAML parsing and expansion in `AppConfig.hpp`. Delegated all file-based overrides to the Go bridge.
- **Networking Hardening**: Implemented "Docker Guard" suppression in Go `NewGRPCServer`. Binding addresses are now forced to `0.0.0.0` in container environments. Verified with `grpc_server_test.go`.
- **Deployment**: Committed and pushed all changes to the `develop` branch for both `distributed-config` and `microservice-toolbox` repositories.


### [SCAN] Role: DocMaintainer | State: Maintenance Completed
- **Version Management**: Updated VERSION.txt to 0.0.1.
- **Documentation Audit**: Verified documentation parity and index integrity. No critical drift found in core README/TODO indices.
