# Project TODOs

## Architectural Recommendations

### 1. Unified Lifecycle Manager (Python & Rust)
Currently, only the `Go` implementation of the `microservice-toolbox` contains the `lifecycle` package (`microservice-toolbox/go/pkg/lifecycle`). This module is highly effective at catching OS signals (`SIGINT`, `SIGTERM`) and orchestrating graceful termination across sub-routines.

**Action Required**: 
- Replicate the `lifecycle.Manager` behavior in both Python and Rust.
- This will ensure that all microservices drop connections safely, flush `msgpack`/`json` logs uniformly, and prevent container zombie-states in Kubernetes/Docker Swarm.