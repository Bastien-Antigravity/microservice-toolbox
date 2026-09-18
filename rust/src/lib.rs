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
