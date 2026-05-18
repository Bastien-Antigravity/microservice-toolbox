use std::sync::Arc;
use tokio::sync::Mutex;
use std::future::Future;
use std::pin::Pin;
use crate::utils::logger::{Logger, ensure_safe_logger};

pub type CleanupResult = Result<(), Box<dyn std::error::Error + Send + Sync>>;
pub type ShutdownFunc = Box<dyn Fn() -> Pin<Box<dyn Future<Output = CleanupResult> + Send>> + Send + Sync>;

struct CleanupEntry {
    name: String,
    func: ShutdownFunc,
}

pub struct LifecycleManager {
    cleanups: Arc<Mutex<Vec<CleanupEntry>>>,
    logger: Arc<dyn Logger>,
}

impl LifecycleManager {
    pub fn new(logger: Option<Arc<dyn Logger>>) -> Self {
        Self {
            cleanups: Arc::new(Mutex::new(Vec::new())),
            logger: ensure_safe_logger(logger),
        }
    }

    pub async fn register<F, Fut>(&self, name: &str, f: F)
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: Future<Output = CleanupResult> + Send + 'static,
    {
        let mut cleanups = self.cleanups.lock().await;
        cleanups.push(CleanupEntry {
            name: name.to_string(),
            func: Box::new(move || Box::pin(f())),
        });
    }

    pub async fn wait(&self) {
        let ctrl_c = tokio::signal::ctrl_c();
        
        #[cfg(unix)]
        let terminate = async {
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .expect("failed to install signal handler")
                .recv()
                .await;
        };

        #[cfg(not(unix))]
        let terminate = std::future::pending::<()>();

        tokio::select! {
            _ = ctrl_c => {
                self.logger.info("Lifecycle: Received SIGINT. Initiating graceful shutdown...");
            }
            _ = terminate => {
                self.logger.info("Lifecycle: Received SIGTERM. Initiating graceful shutdown...");
            }
        }

        self.execute_cleanups().await;
    }

    pub async fn execute_cleanups(&self) {
        let mut cleanups = self.cleanups.lock().await;
        // Execute cleanups in reverse order (LIFO)
        while let Some(entry) = cleanups.pop() {
            self.logger.info(&format!("Lifecycle: Running cleanup '{}'...", entry.name));
            if let Err(e) = (entry.func)().await {
                self.logger.error(&format!("Lifecycle: Cleanup '{}' failed: {:?}", entry.name, e));
            }
        }
        self.logger.info("Lifecycle: Clean shutdown completed.");
    }
}

pub fn new_manager(logger: Option<Arc<dyn Logger>>) -> LifecycleManager {
    LifecycleManager::new(logger)
}
