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

pub mod args;
pub mod loader;
pub mod merger;
pub mod ffi;

pub use loader::load_config;
