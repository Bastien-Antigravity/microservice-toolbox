# Microservice Toolbox - C++ Module (C++17 & C11)

A high-performance header-only C++17 infrastructure library (plus zero-dependency C11/C99 contract headers) for the Bastien-Antigravity ecosystem, providing 1:1 behavioral parity with the Go reference implementation.

## Features
- **In-memory Mirroring**: Full state sync from the Go CGO Bridge (`libdistconf`) for sub-millisecond lookups.
- **Hardened Decryption**: Standardized RSA decryption via the Go engine for `ENC(...)` blocks.
- **Resilient Networking**: Automated reconnection with multiplicative backoff and randomized jitter.
- **Business Standards**: Standardized structures for Market Data and Signals with `snake_case` JSON compatibility.

## Core Components

### 1. Configuration (`AppConfig`)
Provides a hardened API for the "Hierarchy of Truth" and dynamic updates.

```cpp
#include "microservice_toolbox/config/AppConfig.hpp"

using namespace microservice_toolbox::config;

// Initialize session (standalone or fleet)
auto ac = LoadConfig("standalone");

// Resolve version directly from AppConfig (VERSION.txt only, fail-fast)
std::string ver = ac->GetVersion();

// High-level config-verbatim address resolution (from AppConfig)
std::string addr = ac->GetListenAddr("market-observer");

// Decrypt secrets just-in-time
std::string dbPwd = ac->DecryptSecret("ENC(...)");
```

### 2. Connection Manager (`conn_manager`)
Wraps `SafeSocket` to provide self-healing TCP connections with lock-free atomic `Endpoint` snapshots (`std::atomic_load` / `std::atomic_store`) and live `AppConfig` capability resolution.

```cpp
#include "microservice_toolbox/conn_manager/NetworkManager.hpp"

using namespace microservice_toolbox::conn_manager;

auto nm = NetworkManager::New(ac, logger);

// Returns a resilient wrapper bound directly to AppConfig capability
auto mc = nm->ConnectCapability("log_server", "tcp-hello:my-service");

mc->Send({0x01, 0x02, 0x03});
```

### 3. Business Models
Standardized data structures for cross-repo serialization.

```cpp
#include "microservice_toolbox/business/Models.hpp"

using namespace microservice_toolbox::business;

Signal sig;
sig.symbol = "BTC/USDT";
sig.type = SignalType::Buy;

// Generates snake_case JSON for Go/Python/Rust compatibility
nlohmann::json j = sig.to_json();
```

### 4. Direct Notification Client (`NotificationClient`)
Header-only RAII client enabling C++ L2/L3 services to dispatch direct alerts to `notif-server` (gRPC port 1027) via the dynamic `libnotif` C ABI bridge with zero-silent-fallback guarantees.

```cpp
#include "microservice_toolbox/notification/NotificationClient.hpp"

using namespace microservice_toolbox::notification;

// 1. Initialize fail-fast from AppConfig (resolves capabilities.notif_server.grpc_port)
auto notif = NotificationClient::FromConfig(*ac, logger);

// 2. Dispatch 1-line general alert
notif.Send("Risk engine warmed up and executing", {"telegram"});

// 3. Dispatch categorized alert with severity level
notif.SendAlert("TRADE", "Filled limit order: BUY 1.5 BTC @ 64500", {"telegram", "discord"});

// 4. Dispatch full alert with attachment
notif.SendWithAttachment("REPORT", "Daily risk report generated", "risk.pdf", {"reports"});
```

### 5. Declarative `ServiceSpec` & Exchange Contracts (`spec.hpp`, `contracts.hpp`, `contracts.h`)
Standardizes OpenMFE boot registration (`SpecPublisher::PublishWithLifecycle`) and authoritative microservice-owned Exchange Contract serialization across both **C++17** and **pure C11/C99**:

```cpp
// C++17: Build contracts from embedded .proto/.capnp and register with web-interface
#include "microservice_toolbox/spec/spec.hpp"
using namespace microservice_toolbox::spec;

auto ops = ExtractProtoTextOperations(EMBEDDED_PROTO_SCHEMA);
ExchangeContract grpcContract{
    .id = "grpc", .type = "gRPC / Protobuf", .tabLabel = "gRPC Control",
    .address = DisplayAddress(grpcAddr), .port = ResolveContractPort(grpcAddr),
    .operations = ops, .schemaFormat = "proto3", .schema = EMBEDDED_PROTO_SCHEMA
};

auto envelope = NewContractsEnvelope("my_cpp_service", ac->GetVersion(), "my.proto", {grpcContract});
std::string httpBody = envelope.ToJson().dump();

// 5. Spec & Contracts auto-enrich URL, ports, node, and version (via ac->GetVersion())
ServiceSpec spec;
spec.contracts = {grpcContract};
// Populate name, tag, layer, category, description, docLink, protocol, framing...
SpecPublisher::PublishWithLifecycle(*ac, logger, &lm, "my_cpp_service", spec);
```

For pure **C11/C99** services or CGO/FFI wrappers, include `microservice_toolbox/spec/contracts.h` (`MtExchangeContract`, `MtContractsEnvelope`, `mt_exchange_contract_to_json`, `mt_contracts_envelope_to_json`, `mt_spec_free_string`).

### 6. Real-Time Transport WireTap (`WireTap.hpp`), `LifecycleManager` & `Connectivity::Resolver`
- **WireTap**: Lock-free telemetry aggregator (`wiretap::ConfigureFromConfig`, `SetEnabled`/`IsEnabled`, `RecordEvent`, `Snapshot`).
- **Lifecycle**: `lifecycle::LifecycleManager` for SIGINT/SIGTERM handling and LIFO shutdown hooks.
- **Connectivity**: `connectivity::Resolver` for config-verbatim IP/host/port validation (fail-fast on empty).

## Build Requirements
- **C++17** compatible compiler (Clang/GCC) and **C11** compiler (`cc`) for pure C contract headers.
- **libdistconf**: The Go-based CGO bridge library.
- **nlohmann/json**: Header-only JSON library (included for C++; zero external dependencies for `contracts.h`).

## Testing
Run the C++ parity suite:
```bash
make test
```
