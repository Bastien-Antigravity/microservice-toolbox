use tokio::net::TcpStream;
use tokio::io::AsyncWriteExt;
use tokio::sync::Mutex;
use std::sync::Arc;
use tokio::time::sleep;
use crate::conn_manager::manager::NetworkManager;
use crate::conn_manager::errors::Error;

#[derive(Clone)]
pub struct ManagedConnection {
    pub ip: String,
    pub port: String,
    pub nm: Arc<NetworkManager>,
    pub current_conn: Arc<Mutex<Option<TcpStream>>>,
}

impl ManagedConnection {
    pub fn new(ip: String, port: String, nm: Arc<NetworkManager>) -> Self {
        Self {
            ip,
            port,
            nm,
            current_conn: Arc::new(Mutex::new(None)),
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

        let stream = conn_lock.as_mut().unwrap();
        match stream.write_all(data).await {
            Ok(_) => Ok(data.len()),
            Err(e) => {
                println!("ManagedConnection: Write failed ({:?}). Reconnecting...", e);
                *conn_lock = None;
                drop(conn_lock);

                // Reconnect and retry once
                self.reconnect().await?;
                
                let mut conn_lock = self.current_conn.lock().await;
                let stream = conn_lock.as_mut().unwrap();
                stream.write_all(data).await.map_err(|e| {
                    Error::WriteFailed(format!("Retry failed: {:?}", e))
                })?;
                Ok(data.len())
            }
        }
    }

    pub async fn reconnect(&self) -> Result<(), Error> {
        let mut delay = self.nm.base_delay;

        loop {
            match self.nm.establish_connection(&self.ip, &self.port).await {
                Ok(stream) => {
                    println!("ManagedConnection: Reconnected to {}:{}", self.ip, self.port);
                    let mut conn_lock = self.current_conn.lock().await;
                    *conn_lock = Some(stream);
                    return Ok(());
                }
                Err(e) => {
                    if let Some(ref handler) = self.nm.on_error.0 {
                        handler("NetworkManager", "ManagedConnection.reconnect", &e, &format!("Failed to recover connection to {}:{}", self.ip, self.port));
                    }
                    
                    sleep(delay).await;
                    delay = std::cmp::min(delay * 2, self.nm.max_delay);
                    if delay > self.nm.max_delay {
                        delay = self.nm.max_delay;
                    }
                }
            }
        }
    }

    pub async fn close(&self) {
        let mut conn_lock = self.current_conn.lock().await;
        *conn_lock = None;
    }
}
