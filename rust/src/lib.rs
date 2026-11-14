// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: lib.rs.
//
// DATA FLOW:
// Callers -> lib.rs -> Processed Output
//
// KEY PARAMETERS:
// - Standard module parameters.
// -----------------------------------------------------------------------------

pub mod business;
pub mod config;
pub mod conn_manager;
pub mod connectivity;
pub mod lifecycle;
pub mod network;
pub mod serializers;
pub mod utils;
pub mod messaging;
pub mod teleremote;
pub mod notification;
pub mod version;
pub mod spec;
pub mod wiretap;

pub mod contracts {
    pub use crate::spec::{
        ContractOperation,
        ContractPeer,
        ContractsEnvelope,
        ExchangeContract,
        build_contracts_envelope,
        display_address,
        extract_capnp_operations,
        extract_proto_operations,
        new_contracts_envelope,
        read_schema_file,
        resolve_contract_port,
    };
}

// Re-export logger at crate root for 100% parity with Go and Python
pub use utils::logger;


