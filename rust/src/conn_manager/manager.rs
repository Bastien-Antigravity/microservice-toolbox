// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Manages polyglot inter-service network connections with lifecycle hooks and circuit breakers.
//
// DATA FLOW:
// Service Request -> Connection Pool / ManagedConnection -> Active Inter-service Link
//
// KEY PARAMETERS:
// - connections: Active managed connections map.
// - strategies: Backoff and retry presets.
// -----------------------------------------------------------------------------

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
pub type ReloadHandler = Arc<dyn Fn(isize) -> Result<(String, String), Error> + Send + Sync>;
 
/// ConnectionMode defines how the manager handles the initial connection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectionMode {
    /// ModeBlocking blocks until connection is successful (or MaxRetries reached).
    Blocking,
    /// ModeNonBlocking returns immediately and retries in the background.
    NonBlocking,
    /// ModeIndefinite blocks indefinitely until connection is successful.
    Indefinite,
}

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
    pub on_reload_config: Option<ReloadHandler>,
    pub app_config: Option<Arc<std::sync::Mutex<crate::config::loader::AppConfig>>>,
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
        Self::new_with_all(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter, None, None, None)
    }

    // NOTE: This constructor exceeds the Clippy limit of 7 arguments.
    // We intentionally allow this to maintain 1:1 API parity with the Go and Python 
    // implementations of the toolbox, ensuring a consistent developer experience 
    // across the polyglot ecosystem.
    #[allow(clippy::too_many_arguments)]
    pub fn new_with_all(
        max_retries: isize,
        base_delay_ms: u64,
        max_delay_ms: u64,
        connect_timeout_ms: u64,
        backoff: f64,
        jitter: f64,
        on_error: Option<OnErrorHandler>,
        logger: Option<Arc<dyn Logger>>,
        on_reload_config: Option<ReloadHandler>,
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
            on_reload_config,
            app_config: None,
        }
    }

    pub async fn establish_connection(&self, address: &str) -> Result<TcpStream, Error> {
        match tokio::time::timeout(self.connect_timeout, TcpStream::connect(address)).await {
            Ok(Ok(stream)) => Ok(stream),
            Ok(Err(e)) => Err(Error::Io(e)),
            Err(_) => Err(Error::Io(std::io::Error::new(std::io::ErrorKind::TimedOut, "Connect timeout"))),
        }
    }

    pub async fn establish_connection_raw(&self, ip: &str, port: &str) -> Result<TcpStream, Error> {
        let clean_ip = ip.trim_matches('"');
        let clean_port = port.trim_matches('"');
        let address = format!("{}:{}", clean_ip, clean_port);
        self.establish_connection(&address).await
    }

    pub fn get_next_delay(&self, attempt: isize) -> Duration {
        let mut current_delay = self.base_delay.as_secs_f64() * self.backoff.powi(attempt as i32);
        if current_delay > self.max_delay.as_secs_f64() {
            current_delay = self.max_delay.as_secs_f64();
        }

        // Apply jitter
        if self.jitter > 0.0 {
            let jitter_val = rand::thread_rng().gen_range(0.0..(self.jitter * current_delay));
            current_delay += jitter_val;
        }

        Duration::from_secs_f64(current_delay)
    }

    pub async fn connect_with_retry(
        self: Arc<Self>,
        ip: String,
        port: String,
    ) -> Result<ManagedConnection, Error> {
        let mut mc = ManagedConnection::new(ip, port, self.clone());

        let mut last_error = None;

        let mut i = 0;
        while self.max_retries == -1 || i < self.max_retries {
            let attempt = i + 1;
            if attempt % 3 == 0 {
                mc.trigger_reload(attempt).await;
            }

            let ep = mc.endpoint().await;

            match self.establish_connection(&ep.address).await {
                Ok(stream) => {
                    mc.set_stream(stream).await;
                    return Ok(mc);
                }
                Err(e) => {
                    if let OptionalHandler(Some(ref hook)) = self.on_error {
                        hook(attempt, &e, "NetworkManager", &format!("Initial connection failure to {}", ep.address));
                    }
                    last_error = Some(e);
                    
                    let sleep_duration = self.get_next_delay(i);

                    self.logger.info(&format!(
                        "ManagedConnection: Initial connection to {} failed. Retrying in {:?}...",
                        ep.address, sleep_duration
                    ));
                    sleep(sleep_duration).await;
                    i += 1;
                }
            }
        }

        let ep = mc.endpoint().await;
        Err(Error::MaxRetriesReached(format!(
            "Failed to connect to {} after {} attempts. Last error: {:?}",
            ep.address, self.max_retries, last_error
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
        let mc = ManagedConnection::new(ip, port, self);
        let mc_clone = mc.clone();
        
        tokio::spawn(async move {
            if let Err(e) = mc_clone.reconnect().await {
                let (cur_ip, cur_port) = mc_clone.get_endpoint().await;
                if let OptionalHandler(Some(ref handler)) = mc_clone.nm.on_error {
                    handler(1, &e, "NetworkManager", &format!("Failed to connect to {}:{}", cur_ip, cur_port));
                }
            }
        });
        
        mc
    }
 
    pub async fn connect(
        self: Arc<Self>,
        ip: String,
        port: String,
        mode: ConnectionMode,
    ) -> ManagedConnection {
        match mode {
            ConnectionMode::Blocking => {
                match self.clone().connect_with_retry(ip.clone(), port.clone()).await {
                    Ok(mc) => mc,
                    Err(_) => ManagedConnection::new(ip, port, self.clone()),
                }
            }
            ConnectionMode::NonBlocking => self.connect_non_blocking(ip, port),
            ConnectionMode::Indefinite => self.connect_blocking(ip, port).await,
        }
    }

    pub async fn connect_capability(
        self: Arc<Self>,
        capability: &str,
        mode: ConnectionMode,
    ) -> Result<ManagedConnection, Error> {
        let ac = self.app_config.as_ref().ok_or_else(|| {
            Error::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("NetworkManager: AppConfig is None, cannot resolve capability '{}'", capability),
            ))
        })?;

        let (ip, port, public_ip, profile) = {
            let ac_guard = ac.lock().unwrap();
            let addr = ac_guard.get_listen_addr(capability).map_err(|e| {
                Error::Io(std::io::Error::new(std::io::ErrorKind::NotFound, e))
            })?;
            let parts: Vec<&str> = addr.rsplitn(2, ':').collect();
            if parts.len() != 2 {
                return Err(Error::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    format!("Invalid address '{}' for capability '{}'", addr, capability),
                )));
            }
            (parts[1].to_string(), parts[0].to_string(), ac_guard.get_public_ip(), ac_guard.profile.clone())
        };

        let ep = crate::conn_manager::connection::Endpoint::new(ip, port, public_ip, profile);
        let mut mc = ManagedConnection::new_with_endpoint(ep, self.clone());
        mc.app_config = Some(ac.clone());
        mc.capability = Some(capability.to_string());

        match mode {
            ConnectionMode::NonBlocking => {
                let mc_clone = mc.clone();
                tokio::spawn(async move {
                    let _ = mc_clone.reconnect().await;
                });
                Ok(mc)
            }
            _ => {
                mc.reconnect().await?;
                Ok(mc)
            }
        }
    }
}
 
// -----------------------------------------------------------------------------
// Strategies
 
impl NetworkManager {
    /// NewWithConfig creates a manager configured with AppConfig capability resolution.
    pub fn new_with_config(ac: Arc<std::sync::Mutex<crate::config::loader::AppConfig>>, logger: Option<Arc<dyn Logger>>) -> Arc<Self> {
        Arc::new(Self {
            max_retries: 5,
            base_delay: Duration::from_millis(200),
            max_delay: Duration::from_millis(5000),
            connect_timeout: Duration::from_millis(2000),
            backoff: 2.0,
            jitter: 0.0,
            on_error: OptionalHandler(None),
            logger: ensure_safe_logger(logger),
            on_reload_config: None,
            app_config: Some(ac),
        })
    }

    /// NewCriticalStrategy creates a manager configured for critical services: 
    /// Infinite retries, aggressive backoff.
    pub fn new_critical(logger: Option<Arc<dyn Logger>>) -> Arc<Self> {
        new_network_manager_with_all(-1, 200, 10000, 5000, 2.0, 0.2, None, logger, None)
    }
 
    /// NewStandardStrategy creates a manager for standard services:
    /// Limited retries, moderate backoff.
    pub fn new_standard(logger: Option<Arc<dyn Logger>>) -> Arc<Self> {
        new_network_manager_with_all(10, 500, 30000, 5000, 1.5, 0.1, None, logger, None)
    }
 
    /// NewPerformanceStrategy creates a manager for high-performance services:
    /// Short timeouts, low delay, background reconnection.
    pub fn new_performance(logger: Option<Arc<dyn Logger>>) -> Arc<Self> {
        new_network_manager_with_all(-1, 100, 2000, 1000, 1.2, 0.0, None, logger, None)
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

pub fn new_network_manager_with_config(
    ac: Arc<std::sync::Mutex<crate::config::loader::AppConfig>>,
    logger: Option<Arc<dyn Logger>>,
) -> Arc<NetworkManager> {
    NetworkManager::new_with_config(ac, logger)
}

// NOTE: Matches NetworkManager::new_with_all argument count for polyglot parity.
#[allow(clippy::too_many_arguments)]
pub fn new_network_manager_with_all(
    max_retries: isize,
    base_delay_ms: u64,
    max_delay_ms: u64,
    connect_timeout_ms: u64,
    backoff: f64,
    jitter: f64,
    on_error: Option<OnErrorHandler>,
    logger: Option<Arc<dyn Logger>>,
    on_reload_config: Option<ReloadHandler>,
) -> Arc<NetworkManager> {
    Arc::new(NetworkManager::new_with_all(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter, on_error, logger, on_reload_config))
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
            Some(on_error), None, None
        );
        
        // This will fail (port 9999)
        let _result = nm.clone().connect_with_retry("127.0.0.1".to_string(), "9999".to_string()).await;
        
        assert_eq!(retry_count.load(Ordering::SeqCst), 2);
        assert_eq!(last_attempt.load(Ordering::SeqCst), 2);
    }
 
    #[tokio::test]
    async fn test_strategies_presets() {
        let nm_crit = NetworkManager::new_critical(None);
        assert_eq!(nm_crit.max_retries, -1);
        assert_eq!(nm_crit.jitter, 0.2);
 
        let nm_std = NetworkManager::new_standard(None);
        assert_eq!(nm_std.max_retries, 10);
 
        let nm_perf = NetworkManager::new_performance(None);
        assert_eq!(nm_perf.base_delay.as_millis(), 100);
    }
 
    #[tokio::test]
    async fn test_unified_connect() {
        let nm = new_network_manager(2, 10, 50, 50, 1.0, 0.0);
        let ip = "127.0.0.1".to_string();
        let port = "9999".to_string();
 
        // Test NonBlocking
        let start = std::time::Instant::now();
        let _mc = nm.clone().connect(ip.clone(), port.clone(), ConnectionMode::NonBlocking).await;
        let elapsed = start.elapsed();
        assert!(elapsed.as_millis() < 50, "connect(Mode::NonBlocking) took too long: {:?}", elapsed);
 
        // Test Indefinite
        use std::sync::atomic::{AtomicUsize, Ordering};
        let error_count = Arc::new(AtomicUsize::new(0));
        let ec_clone = error_count.clone();
        
        let on_error = Arc::new(move |_attempt, _err: &(dyn std::error::Error + Send + Sync), _src: &str, _msg: &str| {
            ec_clone.fetch_add(1, Ordering::SeqCst);
        });
 
        let nm_indef = new_network_manager_with_all(2, 10, 50, 50, 1.0, 0.0, Some(on_error), None, None);
        
        // Run in background task
        tokio::spawn(async move {
            nm_indef.connect(ip, port, ConnectionMode::Indefinite).await;
        });
 
        tokio::time::sleep(Duration::from_millis(500)).await;
        assert!(error_count.load(Ordering::SeqCst) > 2);
    }

    #[tokio::test]
    async fn test_managed_connection_reconnect_max_retries() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        let error_count = Arc::new(AtomicUsize::new(0));
        let ec_clone = error_count.clone();

        let on_error = Arc::new(move |_attempt, _err: &(dyn std::error::Error + Send + Sync), _src: &str, _msg: &str| {
            ec_clone.fetch_add(1, Ordering::SeqCst);
        });

        let nm = new_network_manager_with_all(
            2, 10, 50, 50, 1.0, 0.0,
            Some(on_error), None, None
        );

        let mc = nm.clone().connect(
            "127.0.0.1".to_string(),
            "9999".to_string(),
            ConnectionMode::Indefinite,
        ).await;

        let res = mc.write(b"hello").await;
        assert!(res.is_err());
        match res.unwrap_err() {
            Error::MaxRetriesReached(_) => {}
            other => panic!("Expected MaxRetriesReached error, got {:?}", other),
        }

        assert_eq!(error_count.load(Ordering::SeqCst), 5);
    }

    #[tokio::test]
    async fn test_managed_connection_3_try_reload() {
        use std::sync::atomic::{AtomicBool, Ordering};
        let reload_called = Arc::new(AtomicBool::new(false));
        let rc_clone = reload_called.clone();

        let reload_handler = Arc::new(move |attempt: isize| {
            if attempt == 3 {
                rc_clone.store(true, Ordering::SeqCst);
                Ok(("127.0.0.1".to_string(), "9999".to_string()))
            } else {
                Err(Error::Io(std::io::Error::new(std::io::ErrorKind::Other, "attempt not 3")))
            }
        });

        let nm = new_network_manager_with_all(
            4, 10, 50, 50, 1.0, 0.0,
            None, None, Some(reload_handler),
        );

        let mc = ManagedConnection::new("127.0.0.1".to_string(), "8080".to_string(), nm.clone());
        let _ = mc.reconnect().await;

        assert!(reload_called.load(Ordering::SeqCst));
        let (ip, port) = mc.get_endpoint().await;
        assert_eq!(ip, "127.0.0.1");
        assert_eq!(port, "9999");
    }

    #[tokio::test]
    async fn test_connect_capability_resolution() {
        let yaml_str = r#"
common:
  name: test-app
  public_ip: "198.51.100.1"
capabilities:
  log-server:
    ip: "127.0.0.1"
    port: "8080"
"#;
        let data: serde_yml::Value = serde_yml::from_str(yaml_str).unwrap();
        let ac = Arc::new(std::sync::Mutex::new(crate::config::loader::AppConfig::from_value(data)));
        let nm = new_network_manager_with_config(ac, None);
        
        let mc_res = nm.connect_capability("log-server", ConnectionMode::NonBlocking).await;
        assert!(mc_res.is_ok());
        let mc = mc_res.unwrap();
        let (ip, port) = mc.get_endpoint().await;
        assert_eq!(ip, "127.0.0.1");
        assert_eq!(port, "8080");
        assert_eq!(mc.capability, Some("log-server".to_string()));
    }
}
