# Integration Tests: Polyglot Matrix

This directory contains the cross-language validation suite that ensures serialization parity across the Bastien-Antigravity fleet.

## Business Data Standardization

The `microservice-toolbox` enforces a unified data standard for the business logic tier, enabling seamless data flow between services written in different languages.

### Implementation Status
- **Go**: Reference implementation in `pkg/business`.
- **Python**: Parity implementation in `microservice_toolbox.business.models`.
- **Rust**: Parity implementation in `src/business/models.rs`.
- **C++**: Parity implementation in `Models.hpp`.

### Integration Matrix (`run_tests.sh`)
The matrix validates that any language can produce data that any other language can consume, using both **JSON** and **MessagePack** formats.

**Validated Models:**
- **MarketEvent**: L1/L2 Market Data envelope.
- **OHLCV**: Time-series Bar representation.
- **Signal**: Strategy generated signals.

## Running the Matrix
Ensure all language environments are set up and the Go bridge is compiled:

```bash
chmod +x run_tests.sh
./run_tests.sh
```

Success is mandatory for all Pull Requests. The matrix verifies the **Mirroring Mandate** at the wire-protocol level.
