use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JetStreamConfig {
    pub enabled: bool,
    pub stream_name: String,
    pub subjects: Vec<String>,
    pub retention: String,
    pub storage: String,
    pub replicas: i32,
    pub max_age_secs: u64,
    pub max_msgs: i64,
    pub max_bytes: i64,
    pub max_msg_size: i32,
    pub durable_consumer: String,
    pub ack_wait_secs: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NatsConfig {
    pub servers: Vec<String>,
    pub subject: String,
    pub cluster_id: String,
    pub client_id: String,
    pub connect_timeout_secs: u64,
    pub reconnect_wait_secs: u64,
    pub max_reconnects: usize,
    pub flush_timeout_secs: u64,
    pub subject_prefix: String,
    pub jetstream: Option<JetStreamConfig>,
}
