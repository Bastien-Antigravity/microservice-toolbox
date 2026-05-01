# Project TODOs

## Architectural Recommendations

### 1. Configuration Parity [COMPLETE]
Achieved 100% feature parity for `distributed-config` integration across Go, Python, and Rust, including Live Updates, Registry Sync, and RSA Decryption offloading.

### 2. Unified Lifecycle Manager (Python & Rust) [IN PROGRESS]
Currently, only the `Go` implementation of the `microservice-toolbox` contains the `lifecycle` package (`microservice-toolbox/go/pkg/lifecycle`). This module is highly effective at catching OS signals (`SIGINT`, `SIGTERM`) and orchestrating graceful termination across sub-routines.

**Action Required**: 
- Replicate the `lifecycle.Manager` behavior in both Python and Rust.
- This will ensure that all microservices drop connections safely, flush `msgpack`/`json` logs uniformly, and prevent container zombie-states in Kubernetes/Docker Swarm.

### 3. Dynamic Key Discovery
Implement a "smart" context-aware key discovery mechanism across all languages. The goal is to support multi-tenancy on the same host by dynamically determining the private/public key paths based on `common.name` or other identifiers.

### 4. C++ Library Audit & Completion
While basic configuration parity is achieved (v1.9.9), the C++ library still lacks some advanced features present in the Go implementation.
- **Action Required**: Perform a gap analysis of `microservice-toolbox/cpp` against the `Go` core. Implement missing high-level utilities (e.g., advanced connectivity retries, more robust health-check abstractions) to ensure C++ services are first-class citizens.