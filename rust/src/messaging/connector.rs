use std::sync::Arc;
use std::time::Duration;
use crate::utils::logger::{Logger, ensure_safe_logger};
use crate::messaging::config::NatsConfig;

/// Establishes an asynchronous connection to the NATS server and configures event logging.
pub async fn connect(
    cfg: &NatsConfig,
    logger: Option<Arc<dyn Logger>>,
) -> Result<async_nats::Client, async_nats::Error> {
    let log = ensure_safe_logger(logger);

    if cfg.servers.is_empty() {
        return Err(async_nats::Error::from(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "no nats servers configured",
        )));
    }

    let log_disconnect = log.clone();
    let log_reconnect = log.clone();
    let client_id = cfg.client_id.clone();
    let client_id_reconnect = cfg.client_id.clone();

    let reconnect_wait_secs = cfg.reconnect_wait_secs;

    // Configure connection options with standard callbacks and properties
    let client = async_nats::ConnectOptions::new()
        .name(&cfg.client_id)
        .connection_timeout(Duration::from_secs(cfg.connect_timeout_secs))
        .reconnect_delay_callback(move |attempts| {
            log_disconnect.warning(&format!(
                "[{}] NATS disconnected, attempting reconnect (attempt {})...",
                client_id, attempts
            ));
            Duration::from_secs(reconnect_wait_secs)
        })
        .event_callback(move |event| {
            let log_reconnect = log_reconnect.clone();
            let client_id_reconnect = client_id_reconnect.clone();
            async move {
                if let async_nats::Event::Connected = event {
                    log_reconnect.info(&format!("[{}] NATS successfully reconnected", client_id_reconnect));
                }
            }
        })
        .connect(&cfg.servers[0])
        .await?;

    log.info(&format!("[{}] Successfully connected to NATS at {}", cfg.client_id, cfg.servers[0]));
    Ok(client)
}
