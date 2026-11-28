// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Represents a resilient, auto-reconnecting network connection with exponential backoff.
//
// DATA FLOW:
// Network Events -> Reconnect Loop + Backoff -> Active Socket Connection
//
// KEY PARAMETERS:
// - target: Network endpoint address.
// - backoff: Reconnection retry delay with randomized jitter.
// -----------------------------------------------------------------------------

use tokio::net::TcpStream;
use tokio::io::AsyncWriteExt;
use tokio::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};
use tokio::time::sleep;
use crate::conn_manager::manager::NetworkManager;
use crate::conn_manager::errors::Error;

#[derive(Clone, Debug)]
pub struct Endpoint {
    pub ip: String,
    pub port: String,
    pub public_ip: String,
    pub profile: String,
    pub address: String,
}

impl Endpoint {
    pub fn new(ip: String, port: String, public_ip: String, profile: String) -> Self {
        let address = format!("{}:{}", ip, port);
        Self {
            ip,
            port,
            public_ip,
            profile,
            address,
        }
    }
}

#[derive(Clone)]
/// ManagedConnection wraps an asynchronous TCP stream and handles automated recovery.
/// 
/// It provides a 'self-healing' interface that automatically triggers 
/// background reconnections if a network failure is detected during use.
pub struct ManagedConnection {
    pub endpoint: Arc<RwLock<Arc<Endpoint>>>,
    pub nm: Arc<NetworkManager>,
    pub app_config: Option<Arc<std::sync::Mutex<crate::config::loader::AppConfig>>>,
    pub capability: Option<String>,
    pub current_conn: Arc<Mutex<Option<TcpStream>>>,
    closed: Arc<AtomicBool>,
    reconnecting: Arc<Mutex<()>>,
}

impl ManagedConnection {
    pub fn new(ip: String, port: String, nm: Arc<NetworkManager>) -> Self {
        Self::new_with_endpoint(Endpoint::new(ip, port, String::new(), String::new()), nm)
    }

    pub fn new_with_endpoint(ep: Endpoint, nm: Arc<NetworkManager>) -> Self {
        let app_config = nm.app_config.clone();
        Self {
            endpoint: Arc::new(RwLock::new(Arc::new(ep))),
            nm,
            app_config,
            capability: None,
            current_conn: Arc::new(Mutex::new(None)),
            closed: Arc::new(AtomicBool::new(false)),
            reconnecting: Arc::new(Mutex::new(())),
        }
    }

    pub async fn update_endpoint(&self, new_ip: String, new_port: String) {
        self.swap_endpoint(new_ip, new_port);
    }

    pub fn swap_endpoint(&self, new_ip: String, new_port: String) {
        let mut ep_guard = self.endpoint.write().unwrap();
        let next = Endpoint::new(new_ip, new_port, ep_guard.public_ip.clone(), ep_guard.profile.clone());
        *ep_guard = Arc::new(next);
    }

    pub async fn get_endpoint(&self) -> (String, String) {
        let ep = self.endpoint.read().unwrap().clone();
        (ep.ip.clone(), ep.port.clone())
    }

    pub async fn endpoint(&self) -> Endpoint {
        (**self.endpoint.read().unwrap()).clone()
    }

    pub fn current_endpoint(&self) -> Arc<Endpoint> {
        let mut ep = self.endpoint.read().unwrap().clone();
        if let (Some(ac), Some(cap)) = (&self.app_config, &self.capability)
            && let Ok(guard) = ac.lock()
            && let Ok(new_addr) = guard.get_listen_addr(cap)
            && new_addr != ep.address {
                let parts: Vec<&str> = new_addr.rsplitn(2, ':').collect();
                if parts.len() == 2 {
                    drop(guard);
                    self.swap_endpoint(parts[1].to_string(), parts[0].to_string());
                    ep = self.endpoint.read().unwrap().clone();
                }
        }
        ep
    }

    pub async fn set_stream(&mut self, stream: TcpStream) {
        let mut conn = self.current_conn.lock().await;
        *conn = Some(stream);
    }

    pub async fn write(&self, data: &[u8]) -> Result<usize, Error> {
        if self.closed.load(Ordering::Acquire) {
            return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
        }

        let mut conn_lock = self.current_conn.lock().await;

        // If no connection, try to reconnect immediately (blocking)
        if conn_lock.is_none() {
            drop(conn_lock); // Release lock before reconnecting
            self.reconnect().await?;
            if self.closed.load(Ordering::Acquire) {
                return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
            }
            conn_lock = self.current_conn.lock().await;
        }

        let stream = conn_lock.as_mut().ok_or_else(|| {
            Error::WriteFailed("ManagedConnection: stream is not connected".to_string())
        })?;
        match stream.write_all(data).await {
            Ok(_) => Ok(data.len()),
            Err(e) => {
                self.nm.logger.warning(&format!("ManagedConnection: Write failed ({:?}). Reconnecting...", e));
                *conn_lock = None;
                drop(conn_lock);

                // Reconnect and retry once
                self.reconnect().await?;
                if self.closed.load(Ordering::Acquire) {
                    return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
                }

                let mut conn_lock = self.current_conn.lock().await;
                let stream = conn_lock.as_mut().ok_or_else(|| {
                    Error::WriteFailed("ManagedConnection: stream is not connected after reconnect".to_string())
                })?;
                stream.write_all(data).await.map_err(|e| {
                    Error::WriteFailed(format!("Retry failed: {:?}", e))
                })?;
                Ok(data.len())
            }
        }
    }

    pub async fn reconnect(&self) -> Result<(), Error> {
        if self.closed.load(Ordering::Acquire) {
            return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
        }

        let _reconn_guard = self.reconnecting.lock().await;
        if self.closed.load(Ordering::Acquire) {
            return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
        }
        if self.current_conn.lock().await.is_some() {
            return Ok(());
        }

        let mut i = 0;

        loop {
            if self.closed.load(Ordering::Acquire) {
                return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
            }

            let attempt = i + 1;
            let ep = self.current_endpoint();

            match self.nm.establish_connection(&ep.address).await {
                Ok(stream) => {
                    if self.closed.load(Ordering::Acquire) {
                        return Err(Error::NoConnection("ManagedConnection is closed".to_string()));
                    }
                    self.nm.logger.info(&format!("ManagedConnection: Reconnected to {}", ep.address));
                    let mut conn_lock = self.current_conn.lock().await;
                    *conn_lock = Some(stream);
                    return Ok(());
                }
                Err(e) => {
                    if self.nm.max_retries != -1 && i >= self.nm.max_retries {
                        return Err(Error::MaxRetriesReached(format!(
                            "Reached max retries {} for {}",
                            self.nm.max_retries, ep.address
                        )));
                    }

                    if let Some(ref handler) = self.nm.on_error.0 {
                        handler(attempt, &e, "NetworkManager", &format!("Failed to recover connection to {}", ep.address));
                    }
                    
                    let delay = self.nm.get_next_delay(i);
                    sleep(delay).await;
                    i += 1;
                }
            }
        }
    }

    pub async fn close(&self) {
        self.closed.store(true, Ordering::Release);
        let mut conn_lock = self.current_conn.lock().await;
        *conn_lock = None;
    }
}
