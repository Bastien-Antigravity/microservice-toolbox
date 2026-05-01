# Architecture: VBA Microservice Toolbox

The VBA implementation bridges the gap between legacy desktop applications and modern microservice infrastructure.

## 1. Win32 FFI Bridge
VBA interacts with the Go core via the standard Win32 API `Declare` mechanism. 
- The `DistConf.bas` module maps the `libdistconf.dll` exports.
- Strings are converted between VBA's BSTR (Wide) and Go's C-strings using helper utilities in `Toolbox.bas`.

## 2. Session Management
Each instance of the `AppConfig` class manages a unique `uintptr` handle to a Go-side session. This ensures thread-safety (within the limits of VBA) and isolated configuration state.

## 3. Local Configuration
VBA uses a `Scripting.Dictionary` to mirror the `private:` section of local YAML files. 
- A custom "YAML-lite" parser in `LoadLocalOverrides` handles top-level keys.
- This allows VBA apps to store local settings without requiring a full YAML library.

## 4. Environment Expansion
The VBA toolbox implements its own environment variable expansion logic to support the ecosystem standard `${VAR:default}` syntax, using the Windows `Environ()` function.
