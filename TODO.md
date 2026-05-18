# TODO: microservice-toolbox

## 🏗️ Architecture & Refactoring
- [x] Standardize the C++ wrapper to use the Go-bridge expansion logic (FEAT-002).
- [x] Docker Guard for gRPC server builders (Go, Python, Rust parity).
- [x] Log-level mapping: Simplified and standardized logic for cross-language log levels.

## 🧪 Testing & CI/CD
- [x] Cross-language parity tests for YAML expansion (Go, Python, Rust, C++ verified in integration/).
- [ ] Full Matrix Integration: Expand matrix tests to cover all Serializer + Transport combinations.

## ✅ Completed (Verified)
- [x] Initial BDD Spec migration: Moved all legacy specs to Obsidian vault.
- [x] Standardize Business Data Models: MarketEvent, OHLCV, and Signal models are 1:1 across Go, Python, Rust, and C++.
- [x] Standardize Lifecycle Manager across Go, Python, Rust, and C++.
- [x] Resilience Standard: Added randomized jitter and backoff to Reconnect loops (Go, Python, Rust, and C++ policy).
- [x] C++ Parity: Implemented ManagedConnection and orchestration methods (ConnectBlocking, etc).
- [x] Networking Hardening: Implemented "Docker Guard" suppression to prevent broken network binds in containers.
