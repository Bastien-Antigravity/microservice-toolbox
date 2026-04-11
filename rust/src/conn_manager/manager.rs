use tokio::net::TcpStream;
use tokio::time::{sleep, Duration};
use std::sync::Arc;
use crate::conn_manager::connection::ManagedConnection;
use crate::conn_manager::errors::Error;

pub type OnErrorHandler = Arc<dyn Fn(&str, &str, &(dyn std::error::Error + Send + Sync), &str) + Send + Sync>;

pub struct NetworkManager {
    pub max_retries: usize,
    pub base_delay: Duration,
    pub max_delay: Duration,
    pub connect_timeout: Duration,
    pub on_error: OptionalHandler,
}

pub struct OptionalHandler(pub Option<OnErrorHandler>);

impl NetworkManager {
    pub fn new(
        max_retries: usize,
        base_delay_ms: u64,
        max_delay_ms: u64,
        connect_timeout_ms: u64,
    ) -> Self {
        Self {
            max_retries,
            base_delay: Duration::from_millis(base_delay_ms),
            max_delay: Duration::from_millis(max_delay_ms),
            connect_timeout: Duration::from_millis(connect_timeout_ms),
            on_error: OptionalHandler(None),
        }
    }

    pub async fn establish_connection(&self, ip: &str, port: &str) -> Result<TcpStream, Error> {
        let clean_ip = ip.trim_matches('"');
        let clean_port = port.trim_matches('"');
        let address = format!("{}:{}", clean_ip, clean_port);
        
        match tokio::time::timeout(self.connect_timeout, TcpStream::connect(&address)).await {
            Ok(Ok(stream)) => Ok(stream),
            Ok(Err(e)) => Err(Error::Io(e)),
            Err(_) => Err(Error::Io(std::io::Error::new(std::io::ErrorKind::TimedOut, "Connect timeout"))),
        }
    }

    pub async fn connect_with_retry(
        self: Arc<Self>,
        ip: String,
        port: String,
    ) -> Result<ManagedConnection, Error> {
        let mut mc = ManagedConnection::new(ip, port, self.clone());

        let mut delay = self.base_delay;
        let mut last_error = None;

        for _ in 0..self.max_retries {
            match self.establish_connection(&mc.ip, &mc.port).await {
                Ok(stream) => {
                    mc.set_stream(stream).await;
                    return Ok(mc);
                }
                Err(e) => {
                    last_error = Some(e);
                    println!(
                        "ManagedConnection: Initial connection to {}:{} failed. Retrying in {:?}...",
                        mc.ip, mc.port, delay
                    );
                    sleep(delay).await;
                    delay = std::cmp::min(delay * 2, self.max_delay);
                }
            }
        }

        Err(Error::MaxRetriesReached(format!(
            "Failed to connect to {}:{} after {} attempts. Last error: {:?}",
            mc.ip, mc.port, self.max_retries, last_error
        )))
    }

    pub fn connect_blocking(
        self: Arc<Self>,
        ip: String,
        port: String,
    ) -> ManagedConnection {
        let mc = ManagedConnection::new(ip, port, self.clone());
        let mc_clone = mc.clone();
        
        tokio::spawn(async move {
            if let Err(e) = mc_clone.reconnect().await {
                if let OptionalHandler(Some(ref handler)) = mc_clone.nm.on_error {
                    handler("NetworkManager", "connect_blocking", &e, &format!("Failed to connect to {}:{}", mc_clone.ip, mc_clone.port));
                }
            }
        });
        
        mc
    }
}

pub fn new_network_manager(
    max_retries: usize,
    base_delay_ms: u64,
    max_delay_ms: u64,
    connect_timeout_ms: u64,
) -> Arc<NetworkManager> {
    Arc::new(NetworkManager::new(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms))
}
