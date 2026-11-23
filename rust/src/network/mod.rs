// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: mod.rs.
//
// DATA FLOW:
// Callers -> mod.rs -> Processed Output
//
// KEY PARAMETERS:
// - Standard module parameters.
// -----------------------------------------------------------------------------

pub mod grpc_server;
pub mod tls;

pub use tls::{
    build_client_endpoint, build_client_tls_config, is_local_address, normalize_tls_mode,
    should_use_client_tls,
};
