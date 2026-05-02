# TODO: microservice-toolbox

## 🚨 High Priority (Governance Gaps)
- [ ] **Polyglot Discrepancy**: Standardize the C++ wrapper to use the Go-bridge expansion logic instead of manual parsing (FEAT-002). (Approval Required)
- [ ] **Resilience Standard**: Add randomized jitter to the Go `ConnectionManager` to match the FEAT-004 requirement. (Approval Required)

## 🏗️ Architecture & Refactoring
- [ ] Implement consistent log-level mapping across Python and Rust.
- [ ] Finalize Docker Guard suppression for gRPC server builders.

## 🧪 Testing & CI/CD
- [ ] Add cross-language parity tests for YAML expansion.

## ✅ Completed
- [x] Initial BDD Spec migration.