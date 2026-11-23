//! ESSENTIAL PROCESS:
//! Re-exports canonical Exchange Contract types and IDL extractors from spec,
//! together with compile-time embedded Platform Cap'n Proto Schemas (SSoT).
//!
//! DATA FLOW:
//! 1. Embeds canonical logger.capnp and notifier.capnp from go/pkg/schemas (SSoT).
//! 2. Exposes LOGGER_CAPNP_SCHEMA, NOTIFIER_CAPNP_SCHEMA, and extract_capnp_operations.
//!
//! KEY PARAMETERS:
//! - LOGGER_CAPNP_SCHEMA: Canonical LoggerMsg Cap'n Proto IDL text.
//! - NOTIFIER_CAPNP_SCHEMA: Canonical NotifierMsg Cap'n Proto IDL text.

pub use crate::spec::{
    build_contracts_envelope, display_address, extract_capnp_operations, extract_proto_operations,
    new_contracts_envelope, read_schema_file, resolve_contract_port, ContractOperation,
    ContractPeer, ContractsEnvelope, ExchangeContract,
};

//-----------------------------------------------------------------------------------------------

/// Canonical ecosystem Cap'n Proto LoggerMsg schema (SSoT).
pub const LOGGER_CAPNP_SCHEMA: &str = include_str!("../../go/pkg/schemas/logger/logger.capnp");

//-----------------------------------------------------------------------------------------------

/// Canonical ecosystem Cap'n Proto NotifierMsg schema (SSoT).
pub const NOTIFIER_CAPNP_SCHEMA: &str =
    include_str!("../../go/pkg/schemas/notifier/notifier.capnp");
