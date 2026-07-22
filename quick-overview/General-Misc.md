---
microservice: microservice-toolbox
type: general-misc
status: active
language: polyglot
tags:
- '#service/microservice-toolbox'
- '#type/general-misc'
- '#state/active'
- '#ai/ignore'
---

# 📝 Microservice Toolbox — General & Miscellaneous

Supplementary configuration and runtime environment notes for the `microservice-toolbox`.

## Dynamic FFI Loading
To run wrappers that depend on the Go reference implementation (Python, C++), the shared Go binary `libdistconf.dylib` must be built:
```bash
cd go
make build-cgo
```
This outputs `libdistconf.dylib` under `go/pkg/config/cgo/` which is imported by native wrappers at startup.

## Local Configuration overrides
- The namespace prefix `local:` can be declared inside any profile YAML config (e.g. `standalone.yaml`).
- Fields declared under `local:` are not verified by config-server, allowing developers to define system-specific path mappings and local logging configurations safely.
