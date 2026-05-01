# Architecture: Go Microservice Toolbox

The Go implementation serves as the **Reference Implementation** for the entire polyglot ecosystem. It contains the core logic for the "Hierarchy of Truth" and the Docker Guard resolution.

## 1. Hierarchy of Truth
Configuration is resolved in the following priority:
1.  **CLI Flags**: Highest priority (e.g., `--key path/to/private.pem`).
2.  **Environment Variables**: OS-level overrides (e.g., `BASTIEN_PRIVATE_KEY_PATH`).
3.  **Local YAML**: File-based settings (e.g., `standalone.yaml`).
4.  **Remote/Defaults**: Infrastructure-level settings.

## 2. Docker Guard
A specialized networking layer that detects if a service is running inside a Docker container.
- **Native Mode**: Uses resolved IP addresses as-is.
- **Docker Mode**: Automatically rewrites binding addresses to `0.0.0.0` to ensure connectivity through container port mappings, regardless of what the config says.

## 3. Decryption Engine
Integrates directly with `distributed-config` to handle `ENC(...)` blocks. It uses process-local environment variables to discover the RSA keys, allowing for seamless CLI overrides via the `--key` flag.

## 4. Local Configuration (`Local`)
The `AppConfig` struct includes a `Local` map (parsed from the `private:` YAML section). This section is reserved for service-specific, non-synchronized settings.
- `UnmarshalLocal(target)`: Decodes this section into a user-provided struct.
