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
- '#zone/3-fleet'
---
# 📝 Microservice Toolbox — General & Miscellaneous

Supplementary configuration and runtime environment notes for the `microservice-toolbox`.

## Dynamic FFI Loading
To run wrappers that depend on the C-ABI shared libraries (Python, Rust, C++, VBA), ensure the workspace shared libraries are built and discoverable:
- `libdistconf` (from `distributed-config`, override via `LIBDISTCONF_PATH`)
- `libunilog` (from `universal-logger`, override via `LIBUNILOG_PATH`)
- `libnotif` (from `notif-server`, override via `LIBNOTIF_PATH`)

`microservice_toolbox.utils.lib_loader` (Python), `DistConf.hpp` / `NotificationClient.hpp` (C++), `config::ffi` / `notification::ffi` (Rust), and `Toolbox.bas` (VBA) resolve these libraries automatically from workspace candidates or explicit environment overrides.

## Local Configuration overrides
- The namespace prefix `local:` can be declared inside any profile YAML config (e.g. `standalone.yaml`).
- Fields declared under `local:` are not verified by config-server, allowing developers to define system-specific path mappings and local logging configurations safely.
