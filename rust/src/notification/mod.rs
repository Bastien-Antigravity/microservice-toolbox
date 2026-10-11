// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Notification client module for direct multi-channel alerting from Rust services.
//
// DATA FLOW:
// Client Alert -> NotificationClient -> gRPC Protobuf -> notif-server
//
// KEY PARAMETERS:
// - NotificationClient: Resilient gRPC notification client facade.
// -----------------------------------------------------------------------------

pub mod proto {
    tonic::include_proto!("notifservice");
}

pub mod ffi;
pub mod client;

pub use client::NotificationClient;
pub use proto::{NotifRequest, NotifResponse};
