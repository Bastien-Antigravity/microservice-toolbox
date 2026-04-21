use std::sync::Arc;

/// Logger trait defines the standard interface for structured logging across the toolbox.
pub trait Logger: Send + Sync {
    fn debug(&self, msg: &str);
    fn info(&self, msg: &str);
    fn warning(&self, msg: &str);
    fn error(&self, msg: &str);
    fn critical(&self, msg: &str);
}

/// Fallback logger that uses the existing terminal_ui logic.
pub struct DefaultLogger;

impl Logger for DefaultLogger {
    fn debug(&self, msg: &str) { crate::utils::terminal_ui::print_internal_log("DEBUG", "Default", "Default", "0", msg); }
    fn info(&self, msg: &str) { crate::utils::terminal_ui::print_internal_log("INFO", "Default", "Default", "0", msg); }
    fn warning(&self, msg: &str) { crate::utils::terminal_ui::print_internal_log("WARNING", "Default", "Default", "0", msg); }
    fn error(&self, msg: &str) { crate::utils::terminal_ui::print_internal_log("ERROR", "Default", "Default", "0", msg); }
    fn critical(&self, msg: &str) { crate::utils::terminal_ui::print_internal_log("CRITICAL", "Default", "Default", "0", msg); }
}

/// Wrapper for the compiled universal-logger.
#[cfg(feature = "unilog")]
pub struct UniLogger {
    inner: unilog_rs::UniLog,
}

#[cfg(feature = "unilog")]
impl UniLogger {
    pub fn new(inner: unilog_rs::UniLog) -> Self {
        Self { inner }
    }
}

#[cfg(feature = "unilog")]
impl Logger for UniLogger {
    fn debug(&self, msg: &str) { self.inner.debug(msg); }
    fn info(&self, msg: &str) { self.inner.info(msg); }
    fn warning(&self, msg: &str) { self.inner.warning(msg); }
    fn error(&self, msg: &str) { self.inner.error(msg); }
    fn critical(&self, msg: &str) { self.inner.critical(msg); }
}

/// Ensures a valid logger is returned, falling back to `Arc<DefaultLogger>` if None.
pub fn ensure_safe_logger(logger: Option<Arc<dyn Logger>>) -> Arc<dyn Logger> {
    logger.unwrap_or_else(|| Arc::new(DefaultLogger))
}
