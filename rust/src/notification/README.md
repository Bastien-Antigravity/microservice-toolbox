# Notification Client (`rust/src/notification`)

The `notification` module provides a standardized client facade for dispatching direct, multi-channel alerts and business notifications from Rust microservices directly to `notif-server` via the `libnotif` CGO shared library bridge.

## Architectural Role & Port Mapping
- **Target Daemon**: `notif-server`
- **Port**: Auto-discovered dynamically via `app_config.get_grpc_listen_addr("notif_server")` (canonical default `1027`). Strictly fails fast if the capability is missing or unresolvable (zero silent fallback).
- **Core Engine**: Binds dynamically to `notif-server`'s `libnotif` CGO shared library (via `notification::ffi`), mirroring `distconf::ffi`.
- **Contrast with `tele-remote`**:
  - `tele-remote`: Bi-directional interactive control plane (bot menus, button callbacks, commands).
  - `notif-server`: Direct 1-way multi-channel alert dispatch (Telegram, Discord, Email, Webhooks).

---

## Features
- **100% Parity with Go, Python, and C++**: Identical method signatures (`send`, `send_alert`, `send_with_attachment`, `close`).
- **libnotif CGO Bridge**: High-performance C ABI dispatch without requiring heavy tonic/prost compilation overhead.
- **Asynchronous Tokio**: Native async/await support with synchronous helpers (`send_sync`, `send_alert_sync`).
- **Dynamic Port Resolution**: Fully integrates with `AppConfig` and Docker Guard.
- **Fail-Fast Configuration**: Fails immediately on initialization if `notif_server` capability is missing or unresolvable.
- **Two-Tier Logger Compliance**: Constructor wraps injected loggers with `ensure_safe_logger`.

---

## Quickstart & Usage

### 1. Initialization from AppConfig
```rust
use microservice_toolbox::config::loader::AppConfig;
use microservice_toolbox::notification::NotificationClient;

let app_config = AppConfig::default(); // or loaded via fleet bootstrap

// Auto-resolves notif_server gRPC address from capabilities (port 1027)
let notif_client = NotificationClient::from_config(&app_config, None)?;
```

### 2. Sending Alerts
```rust
// 1-line direct notification
notif_client.send("🚀 Rust worker online and healthy", &["telegram"]).await?;

// Categorized alert
notif_client.send_alert("TRADE", "Filled order #1092: Sold 1.5 ETH", &["trade_channel"]).await?;

// Alert with attachment
notif_client.send_with_attachment("REPORT", "Weekly Performance", "/tmp/report.pdf", &["finance"]).await?;
```
