# Project TODOs

## Architectural Recommendations

### 1. Unified Lifecycle Manager (Python & Rust)
Currently, only the `Go` implementation of the `microservice-toolbox` contains the `lifecycle` package (`microservice-toolbox/go/pkg/lifecycle`). This module is highly effective at catching OS signals (`SIGINT`, `SIGTERM`) and orchestrating graceful termination across sub-routines.

**Action Required**: 
- Replicate the `lifecycle.Manager` behavior in both Python and Rust.
- This will ensure that all microservices drop connections safely, flush `msgpack`/`json` logs uniformly, and prevent container zombie-states in Kubernetes/Docker Swarm.

### 2. Dynamic Key Discovery
Implement a "smart" context-aware key discovery mechanism across all languages. The goal is to support multi-tenancy on the same host by dynamically determining the private/public key paths based on `common.name` or other identifiers.