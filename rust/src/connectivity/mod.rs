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

pub mod resolver;

pub use resolver::{Resolver, new_resolver};
