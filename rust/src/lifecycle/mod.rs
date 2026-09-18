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

pub mod manager;

pub use manager::{LifecycleManager, new_manager};
