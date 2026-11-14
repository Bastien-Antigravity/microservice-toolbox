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
use std::sync::Arc;
use tokio::time::sleep;
use crate::conn_manager::manager::{NetworkManager, ReloadHandler};
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
        let clean_ip = ip.trim_matches('"').to_string();
        let clean_port = port.trim_matches('"').to_string();
        let address = format!("{}:{}", clean_ip, clean_port);
        Self {
            ip: clean_ip,
            port: clean_port,
            public_ip: public_ip.trim_matches('"').to_string(),
            profile: profile.trim_matches('"').to_string(),
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
    pub endpoint: Arc<tokio::sync::RwLock<Endpoint>>,
    pub nm: Arc<NetworkManager>,
    pub on_reload: Arc<Mutex<Option<ReloadHandler>>>,
    pub app_config: Option<Arc<std::sync::Mutex<crate::config::loader::AppConfig>>>,
    pub capability: Option<String>,
    pub current_conn: Arc<Mutex<Option<TcpStream>>>,
}

impl ManagedConnection {
    pub fn new(ip: String, port: String, nm: Arc<NetworkManager>) -> Self {
        Self::new_with_endpoint(Endpoint::new(ip, port, String::new(), String::new()), nm)
    }

    pub fn new_with_endpoint(ep: Endpoint, nm: Arc<NetworkManager>) -> Self {
        let reload = nm.on_reload_config.clone();
        let app_config = nm.app_config.clone();
        Self {
            endpoint: Arc::new(tokio::sync::RwLock::new(ep)),
            nm,
            on_reload: Arc::new(Mutex::new(reload)),
            app_config,
            capability: None,
            current_conn: Arc::new(Mutex::new(None)),
        }
    }

    pub async fn update_endpoint(&self, new_ip: String, new_port: String) {
        let mut ep_lock = self.endpoint.write().await;
        *ep_lock = Endpoint::new(new_ip, new_port, ep_lock.public_ip.clone(), ep_lock.profile.clone());
    }

    pub async fn get_endpoint(&self) -> (String, String) {
        let ep = self.endpoint.read().await;
        (ep.ip.clone(), ep.port.clone())
    }

    pub async fn endpoint(&self) -> Endpoint {
        self.endpoint.read().await.clone()
    }

    pub async fn set_reload_handler(&self, handler: ReloadHandler) {
        let mut h_lock = self.on_reload.lock().await;
        *h_lock = Some(handler);
    }

    pub async fn trigger_reload(&self, attempt: isize) {
        if let (Some(ac), Some(cap)) = (&self.app_config, &self.capability) {
            self.nm.logger.warning(&format!(
                "ManagedConnection: 3 failed connection attempts reached (attempt {}). Synchronizing config from server...",
                attempt
            ));
            let new_addr_res = {
                let mut guard = ac.lock().unwrap();
                let _ = guard.sync();
                guard.get_listen_addr(cap)
            };
            match new_addr_res {
                Ok(addr) => {
                    let parts: Vec<&str> = addr.rsplitn(2, ':').collect();
                    if parts.len() == 2 {
                        let new_ip = parts[1].to_string();
                        let new_port = parts[0].to_string();
                        self.update_endpoint(new_ip.clone(), new_port.clone()).await;
                        self.nm.logger.info(&format!(
                            "ManagedConnection: Target address for capability {} updated to {}:{} following config sync",
                            cap, new_ip, new_port
                        ));
                        return;
                    }
                }
                Err(e) => {
                    self.nm.logger.warning(&format!(
                        "ManagedConnection: Config sync for capability {} failed: {}",
                        cap, e
                    ));
                    return;
                }
            }
        }

        let reload_fn = {
            let h_lock = self.on_reload.lock().await;
            h_lock.clone().or_else(|| self.nm.on_reload_config.clone())
        };

        if let Some(handler) = reload_fn {
            self.nm.logger.warning(&format!(
                "ManagedConnection: 3 failed connection attempts reached (attempt {}). Reloading configuration...",
                attempt
            ));
            match handler(attempt) {
                Ok((new_ip, new_port)) => {
                    self.update_endpoint(new_ip.clone(), new_port.clone()).await;
                    self.nm.logger.info(&format!(
                        "ManagedConnection: Target address updated to {}:{} following config reload",
                        new_ip, new_port
                    ));
                }
                Err(e) => {
                    self.nm.logger.warning(&format!(
                        "ManagedConnection: Configuration reload returned error: {:?}",
                        e
                    ));
                }
            }
        }
    }

    pub async fn set_stream(&mut self, stream: TcpStream) {
        let mut conn = self.current_conn.lock().await;
        *conn = Some(stream);
    }

    pub async fn write(&self, data: &[u8]) -> Result<usize, Error> {
        let mut conn_lock = self.current_conn.lock().await;

        // If no connection, try to reconnect immediately (blocking)
        if conn_lock.is_none() {
            drop(conn_lock); // Release lock before reconnecting
            self.reconnect().await?;
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
        let mut i = 0;

        loop {
            let attempt = i + 1;
            if attempt % 3 == 0 {
                self.trigger_reload(attempt).await;
            }

            let ep = self.endpoint().await;

            match self.nm.establish_connection(&ep.address).await {
                Ok(stream) => {
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
        let mut conn_lock = self.current_conn.lock().await;
        *conn_lock = None;
    }
}
