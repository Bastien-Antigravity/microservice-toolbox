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

pub mod errors;
pub mod manager;
pub mod connection;

pub use manager::{NetworkManager, new_network_manager};
pub use connection::ManagedConnection;
pub use errors::Error;
