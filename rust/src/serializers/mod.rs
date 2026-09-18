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

pub mod serializer;
pub mod providers;

pub use serializer::Serializer;
pub use providers::{JsonSerializer, BinSerializer, new_json_serializer, new_bin_serializer};
