// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Teleremote client module for dynamic Telegram bot UI registration and telemetry.
//
// DATA FLOW:
// Client Actions / Telemetry -> TeleClient -> gRPC Stream -> TeleRemote Server
//
// KEY PARAMETERS:
// - Action: Interactive Telegram button / menu schema.
// - TeleClient: Resilient gRPC streaming client.
// -----------------------------------------------------------------------------

pub mod proto {
    tonic::include_proto!("teleremote");
}

pub mod client;

pub use client::{Action, ActionCallback, TeleClient};
pub use proto::{BotCommand, ComponentMessage, QueueMessage, Registration};
