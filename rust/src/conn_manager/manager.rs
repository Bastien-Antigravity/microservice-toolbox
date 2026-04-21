use tokio::time::{sleep, Duration};
use tokio::net::TcpStream;
use std::sync::Arc;
use rand::Rng;
use crate::conn_manager::connection::ManagedConnection;
use crate::conn_manager::errors::Error;
use crate::utils::logger::{Logger, ensure_safe_logger};

/// OnErrorHandler is a callback triggered on every connection attempt failure.
/// It receives:
/// - attempt: The current failure count (starting at 1).
/// - error: The specific error that triggered the failure.
/// - source: The component where the error occurred.
/// - msg: A descriptive message providing additional context.
pub type OnErrorHandler = Arc<dyn Fn(isize, &(dyn std::error::Error + Send + Sync), &str, &str) + Send + Sync>;

/// NetworkManager handles reliable connection establishment with retries.
/// 
/// It implements a resilient strategy using:
/// - Multiplicative Backoff: Increasing delay between attempts.
/// - Randomized Jitter: Prevents thundering herd issues in large fleets.
/// - Context-Aware Recovery: Unified error reporting via on_error.
pub struct NetworkManager {
    pub max_retries: isize, // Supports -1 for infinite retries
    pub base_delay: Duration,
    pub max_delay: Duration,
    pub connect_timeout: Duration,
    pub backoff: f64,
    pub jitter: f64, // 0.0 to 1.0
    pub on_error: OptionalHandler,
    pub logger: Arc<dyn Logger>,
}

pub struct OptionalHandler(pub Option<OnErrorHandler>);

impl NetworkManager {
    pub fn new(
        max_retries: isize,
        base_delay_ms: u64,
        max_delay_ms: u64,
        connect_timeout_ms: u64,
        backoff: f64,
        jitter: f64,
    ) -> Self {
        Self::new_with_all(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter, None, None)
    }

    pub fn new_with_all(
        max_retries: isize,
        base_delay_ms: u64,
        max_delay_ms: u64,
        connect_timeout_ms: u64,
        backoff: f64,
        jitter: f64,
        on_error: Option<OnErrorHandler>,
        logger: Option<Arc<dyn Logger>>,
    ) -> Self {
        Self {
            max_retries,
            base_delay: Duration::from_millis(base_delay_ms),
            max_delay: Duration::from_millis(max_delay_ms),
            connect_timeout: Duration::from_millis(connect_timeout_ms),
            backoff,
            jitter,
            on_error: OptionalHandler(on_error),
            logger: ensure_safe_logger(logger),
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

        let _delay = self.base_delay;
        let mut last_error = None;

        let mut i = 0;
        while self.max_retries == -1 || i < self.max_retries {
            match self.establish_connection(&mc.ip, &mc.port).await {
                Ok(stream) => {
                    mc.set_stream(stream).await;
                    return Ok(mc);
                }
                Err(e) => {
                    if let OptionalHandler(Some(ref hook)) = self.on_error {
                        hook(i + 1, &e, "NetworkManager", &format!("Initial connection failure to {}:{}", mc.ip, mc.port));
                    }
                    last_error = Some(e);
                    
                    // Calculate backoff
                    let mut current_delay = self.base_delay.as_secs_f64() * self.backoff.powi(i as i32);
                    if current_delay > self.max_delay.as_secs_f64() {
                        current_delay = self.max_delay.as_secs_f64();
                    }

                    // Apply jitter
                    if self.jitter > 0.0 {
                        let jitter_val = rand::thread_rng().gen_range(0.0..(self.jitter * current_delay));
                        current_delay += jitter_val;
                    }

                    let sleep_duration = Duration::from_secs_f64(current_delay);

                    self.logger.info(&format!(
                        "ManagedConnection: Initial connection to {}:{} failed. Retrying in {:?}...",
                        mc.ip, mc.port, sleep_duration
                    ));
                    sleep(sleep_duration).await;
                    i += 1;
                }
            }
        }

        Err(Error::MaxRetriesReached(format!(
            "Failed to connect to {}:{} after {} attempts. Last error: {:?}",
            mc.ip, mc.port, self.max_retries, last_error
        )))
    }

    pub async fn connect_blocking(
        self: Arc<Self>,
        ip: String,
        port: String,
    ) -> ManagedConnection {
        let mc = ManagedConnection::new(ip.clone(), port.clone(), self.clone());
        if let Err(e) = mc.reconnect().await
            && let OptionalHandler(Some(ref handler)) = self.on_error {
                handler(1, &e, "NetworkManager", &format!("Failed to connect to {}:{}", ip, port));
        }
        mc
    }

    pub fn connect_non_blocking(
        self: Arc<Self>,
        ip: String,
        port: String,
    ) -> ManagedConnection {
        let mc = ManagedConnection::new(ip.clone(), port.clone(), self.clone());
        let mc_clone = mc.clone();
        
        tokio::spawn(async move {
            if let Err(e) = mc_clone.reconnect().await
                && let OptionalHandler(Some(ref handler)) = mc_clone.nm.on_error {
                    handler(1, &e, "NetworkManager", &format!("Failed to connect to {}:{}", mc_clone.ip, mc_clone.port));
            }
        });
        
        mc
    }
}

pub fn new_network_manager(
    max_retries: isize,
    base_delay_ms: u64,
    max_delay_ms: u64,
    connect_timeout_ms: u64,
    backoff: f64,
    jitter: f64,
) -> Arc<NetworkManager> {
    Arc::new(NetworkManager::new(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter))
}

pub fn new_network_manager_with_all(
    max_retries: isize,
    base_delay_ms: u64,
    max_delay_ms: u64,
    connect_timeout_ms: u64,
    backoff: f64,
    jitter: f64,
    on_error: Option<OnErrorHandler>,
    logger: Option<Arc<dyn Logger>>,
) -> Arc<NetworkManager> {
    Arc::new(NetworkManager::new_with_all(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter, on_error, logger))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_connect_non_blocking_returns_immediately() {
        let nm = new_network_manager(5, 100, 1000, 500, 2.0, 0.0);
        let start = std::time::Instant::now();
        let _mc = nm.connect_non_blocking("127.0.0.1".to_string(), "9999".to_string());
        let elapsed = start.elapsed();
        assert!(elapsed.as_millis() < 100, "connect_non_blocking took too long: {:?}", elapsed);
    }

    #[tokio::test]
    async fn test_on_error_unified_hook() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        let retry_count = Arc::new(AtomicUsize::new(0));
        let last_attempt = Arc::new(AtomicUsize::new(0));
        
        let rc_clone = retry_count.clone();
        let la_clone = last_attempt.clone();
        
        let on_error = Arc::new(move |attempt, _err: &(dyn std::error::Error + Send + Sync), _src: &str, _msg: &str| {
            rc_clone.fetch_add(1, Ordering::SeqCst);
            la_clone.store(attempt as usize, Ordering::SeqCst);
        });
        
        let nm = new_network_manager_with_all(
            2, 10, 100, 50, 1.0, 0.0, 
            Some(on_error), None
        );
        
        // This will fail (port 9999)
        let _result = nm.clone().connect_with_retry("127.0.0.1".to_string(), "9999".to_string()).await;
        
        assert_eq!(retry_count.load(Ordering::SeqCst), 2);
        assert_eq!(last_attempt.load(Ordering::SeqCst), 2);
    }
}
