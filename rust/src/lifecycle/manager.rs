// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Manages application lifecycle, OS signal traps (SIGINT, SIGTERM), and orderly LIFO cleanups.
//
// DATA FLOW:
// OS Signals / Shutdown Request -> LifecycleManager::wait() -> LIFO Cleanup Execution -> Process Exit
//
// KEY PARAMETERS:
// - cleanups: Synchronized stack of registered CleanupEntry hooks (executed LIFO).
// - logger: Universal Logger instance for audit logging.
// -----------------------------------------------------------------------------

use crate::utils::logger::{Logger, ensure_safe_logger};
use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use tokio::sync::Notify;

pub type CleanupResult = Result<(), Box<dyn std::error::Error + Send + Sync>>;
pub type ShutdownFunc = Box<dyn Fn() -> Pin<Box<dyn Future<Output = CleanupResult> + Send>> + Send + Sync>;

struct CleanupEntry {
    name: String,
    func: ShutdownFunc,
}

pub struct LifecycleManager {
    cleanups: Arc<Mutex<Vec<CleanupEntry>>>,
    shutdown_notify: Arc<Notify>,
    logger: Arc<dyn Logger>,
}

impl LifecycleManager {
    pub fn new(logger: Option<Arc<dyn Logger>>) -> Self {
        Self {
            cleanups: Arc::new(Mutex::new(Vec::new())),
            shutdown_notify: Arc::new(Notify::new()),
            logger: ensure_safe_logger(logger),
        }
    }

    pub async fn register<F, Fut>(&self, name: &str, f: F)
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: Future<Output = CleanupResult> + Send + 'static,
    {
        self.register_background(name, f);
    }

    /// Synchronously registers an async cleanup hook with zero race against immediate shutdown.
    pub fn register_background<F, Fut>(&self, name: &str, f: F)
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: Future<Output = CleanupResult> + Send + 'static,
    {
        if let Ok(mut guard) = self.cleanups.lock() {
            guard.push(CleanupEntry {
                name: name.to_string(),
                func: Box::new(move || Box::pin(f())),
            });
        }
    }

    /// Wakes `wait()` programmatically to run cleanups.
    pub fn request_shutdown(&self) {
        self.shutdown_notify.notify_waiters();
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
            _ = self.shutdown_notify.notified() => {
                self.logger.info("Lifecycle: Shutdown requested. Initiating graceful shutdown...");
            }
        }

        self.execute_cleanups().await;
    }

    pub async fn execute_cleanups(&self) {
        let mut hooks = {
            match self.cleanups.lock() {
                Ok(mut guard) => std::mem::take(&mut *guard),
                Err(_) => Vec::new(),
            }
        };

        // Execute cleanups in reverse order (LIFO) without holding the mutex across awaits
        while let Some(entry) = hooks.pop() {
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

pub fn new_manager_with_logger(logger: Option<Arc<dyn Logger>>) -> LifecycleManager {
    LifecycleManager::new(logger)
}
