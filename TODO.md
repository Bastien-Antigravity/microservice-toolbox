# TODO: microservice-toolbox

## 🚨 High Priority (Governance Gaps)
- [ ] **Polyglot Discrepancy**: Standardize the C++ wrapper to use the Go-bridge expansion logic instead of manual parsing (FEAT-002). (Approval Required)

## 🏗️ Architecture & Refactoring
- [x] Implement consistent log-level mapping across Python, Rust, and C++.
- [ ] Finalize Docker Guard suppression for gRPC server builders.

## 🧪 Testing & CI/CD
- [ ] Add cross-language parity tests for YAML expansion.

## ✅ Completed
- [x] Initial BDD Spec migration.
- [x] Standardize Business Data Models (MarketEvent, OHLCV, Signal) across Go, Python, Rust, and C++.
- [x] Standardize Lifecycle Manager across Go, Python, Rust, and C++.
- [x] Resilience Standard: Added randomized jitter and backoff to Reconnect loops (Go, Python, Rust, and C++ policy).