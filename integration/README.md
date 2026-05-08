# Integration Tests: Polyglot Matrix

This directory contains scripts and source code for verifying cross-language serialization compatibility.

## Business Data Standardization (WIP)

The `schemas/business` directory contains standardized Cap'n Proto definitions for:
- `MarketEvent` (L1/L2 Market Data)
- `OHLCV` (Time-series Bars)
- `Signal` (Trading Strategy Signals)

### Current Implementation Status
- **Go**: Full support in `microservice-toolbox/go/pkg/business`. Uses JSON serialization as a baseline.
- **Python/Rust**: Pending implementation.

### Integration Strategy
To add these models to the integration matrix:
1. Generate Cap'n Proto bindings for each language.
2. Update `matrix_gen.*` and `matrix_con.*` to include a `business` format test case.
3. Update `run_tests.sh` to include the `business` format.

Verification is currently handled by the `sandbox-testing` suite (`FEAT-004-Unified-Data`).
