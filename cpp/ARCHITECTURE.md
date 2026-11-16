# Architecture: C++17 & C11 Microservice Toolbox

The C++ implementation is designed for maximum performance in latency-sensitive environments while maintaining 100% behavioral parity with the Go reference implementation.

## 1. Full FFI Bridge Sync
To avoid the overhead of crossing the C++/Go bridge for every configuration lookup, `AppConfig` implements a **Full Sync** pattern:
- **Initialization**: Calls `GetFullConfig()` from `libdistconf` once at startup.
- **Mirroring**: The resulting JSON is parsed via header-only `nlohmann/json` into `data_`, with `local` overrides merged cleanly.
- **Lookups**: `GetLocal`, `UnmarshalLocal`, `GetVersion` (`VERSION.txt`-only), and address validation (`GetListenAddr`, `GetGRPCListenAddr`, `GetRESTAddr`) operate fail-fast with zero silent fallbacks.

## 2. Core Modules (100% Parity)
- **Business (`business/Models.hpp`)**: Canonical `MarketEvent` (with RFC 4648 Base64 payload encoding), `Trade`, `Quote`, `OrderBook`, `OHLCV`, `Signal`, plus `WrapMarketEvent`, `Serialize`, `Deserialize`, and `SystemTimestamp`.
- **Spec & Exchange Contracts (`spec/`)**: `spec.hpp` (`ServiceSpec`, `SpecPublisher` with `BuildSpecFromConfig` auto-enrichment & `PublishWithLifecycle`), `contracts.hpp` (`ExchangeContract`, `ContractsEnvelope`, `ExtractProtoTextOperations`, `ExtractCapnpOperations`), and zero-dependency pure C11 header `contracts.h` (`MtExchangeContract`, `MtContractsEnvelope`, `mt_contracts_envelope_to_json`).
- **WireTap (`wiretap/WireTap.hpp`)**: Lock-free transport telemetry aggregator (`ConfigureFromConfig`, `SetEnabled`/`IsEnabled`, `RecordEvent`, `Snapshot`).
- **Notification (`notification/NotificationClient.hpp`)**: Fail-fast direct gRPC alerting client (`FromConfig`) via `libnotif`.
- **Connectivity (`connectivity/Resolver.hpp`)**: Config-verbatim `Resolver` (`ResolveBindAddr`, `ResolveFullBindAddr`) failing fast on empty host/port (never rewriting configured IPs to `0.0.0.0`).
- **Version (`version/Version.hpp`)**: Exposed via `AppConfig::GetVersion()`, resolving strictly from `VERSION.txt` (or `-DAPP_VERSION` compiled from `VERSION.txt`) with zero runtime env overrides or `"0.0.1"` fallbacks.
- **Serializers (`serializers/`)**: `JsonSerializer` & MsgPack serializers.
- **Lifecycle (`lifecycle/LifecycleManager.hpp`)**: Graceful shutdown via signal handling (SIGINT/SIGTERM) and LIFO cleanup execution.
- **Conn Manager (`conn_manager/`)**: Unified `NetworkManager::New(ac, logger)`, immutable precomputed `Endpoint` pointer structure (`ip`, `port`, `public_ip`, `profile`, `address`), 100% lock-free endpoint reads/updates via `std::atomic_load` / `std::atomic_store` on `std::shared_ptr<const Endpoint>`, and direct `AppConfig->GetListenAddr(capability)` resolution on reconnect.

## 3. Decryption Delegation
While config lookups are mirrored, **Decryption** is always delegated back to the Go core (`DistConf::Decrypt`) so private RSA keys remain isolated inside a single cryptographic boundary.

## 4. Hierarchy of Truth
- **CLI Flags & Overrides**: Processed through `LoadConfig("standalone", argc, argv)` (with CLI Docker Guard ignoring `--host`/`--port` overrides inside containers) and `ValidateUniquePorts()`.

## 5. Cold-Path Fail-Fast / Zero Silent Fallback
Required capabilities (`GetListenAddr`, `GetGRPCListenAddr`, `GetRESTAddr`), `VERSION.txt`, and unique port allocations validate upfront and throw explicit `std::runtime_error` diagnostics if missing or conflicting — never falling back silently to `"127.0.0.1"`, `"0.0.0.0"`, or `"0.0.1"`.
