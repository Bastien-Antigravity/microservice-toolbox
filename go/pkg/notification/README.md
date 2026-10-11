# Notification Client (`go/pkg/notification`)

The `notification` package provides a standardized, resilient gRPC client facade for dispatching direct, multi-channel alerts and business notifications from L2 and L3 microservices (e.g. trading bots, schedulers, domain pipelines, AI squad scripts) directly to `notif-server`.

## Architectural Role & Port Mapping
- **Target Daemon**: `notif-server`
- **Port**: `1027` (gRPC Protobuf ingestion: `NotifService.SendNotification`)
- **Address Resolution**: Auto-discovered dynamically via `appConfig.GetGRPCListenAddr("notif_server")`. Strictly fails fast if the capability is missing or unresolvable (zero silent fallback).
- **Contrast with `tele-remote`**:
  - `tele-remote`: Bi-directional interactive control plane (bot menus, button callbacks, commands).
  - `notif-server`: Direct 1-way multi-channel alert dispatch (Telegram, Discord, Email, Webhooks).

---

## Features
- **1-Line API**: Clean methods for direct notifications, typed alerts, and attachments.
- **Dynamic Port Resolution**: Fully integrates with `microservice-toolbox/go/pkg/config` and Docker Guard.
- **Fail-Fast Configuration**: Fails immediately on startup if `notif_server` capability is missing or unresolvable.
- **Resilient gRPC**: Lazy connection with background reconnection and timeout guards.
- **Multi-Channel Tagging**: Directs alerts to specific targets (e.g. `telegram`, `discord`, `trade_channel`).
- **Two-Tier Logger Compliance**: Constructor wraps injected loggers with `EnsureSafeLogger`.

---

## Quickstart & Usage

### 1. Initialization in an L2 / L3 Microservice
```go
package main

import (
	"context"
	"time"

	toolbox_bootstrap "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/bootstrap"
	toolbox_notif "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/notification"
)

func main() {
	// Bootstrap microservice
	appConfig, uniLog := toolbox_bootstrap.BootstrapService("orderbook-aggregator", "store")
	defer uniLog.Close()

	// Initialize Notification Client (resolves notif_server on gRPC port 1027)
	notifClient, err := toolbox_notif.NewClient(appConfig, uniLog)
	if err != nil {
		uniLog.Critical("Failed to initialize notification client: %v", err)
		return
	}
	defer notifClient.Close()
```

### 2. Sending a Direct Notification (1-Line)
```go
ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
defer cancel()

// Untyped notification routed to specific channels or default Telegram
err = notifClient.Send(ctx, "🚀 Orderbook aggregator online and synced", "telegram")
```

### 3. Sending Categorized Domain Alerts (`SendAlert`)
```go
// Specific severity level like TRADE, CRITICAL, WARNING, REPORT
err = notifClient.SendAlert(ctx, "TRADE", "Executed BUY 2.5 BTC @ $64,250", "trade_channel")
```

### 4. Sending Alerts with Attachments (`SendWithAttachment`)
```go
err = notifClient.SendWithAttachment(ctx, "REPORT", "Daily Trading Summary", "/data/reports/daily.pdf", "finance")
```
