// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-level client facade enabling L2 and L3 Rust microservices to send direct,
// multi-channel notifications to notif-server via the libnotif CGO FFI bridge.
//
// DATA FLOW:
// L2/L3 Domain Alert -> NotificationClient.send / send_alert -> libnotif FFI -> notif-server
//
// KEY PARAMETERS:
// - app_config: Shared ecosystem AppConfig dynamically resolving notif_server gRPC capability.
// - target_addr: Target gRPC address (host:port) of notif-server.
// - logger: Unified ecosystem logger instance.
// -----------------------------------------------------------------------------

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use crate::config::loader::AppConfig;
use crate::utils::logger::{ensure_safe_logger, Logger};
use super::ffi;

pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(5);

// -----------------------------------------------------------------------------
// NotificationClient
// -----------------------------------------------------------------------------

/// NotificationClient provides a thread-safe, resilient client for dispatching
/// notifications directly from Rust microservices to notif-server via libnotif.
#[derive(Clone)]
pub struct NotificationClient {
    target_addr: String,
    logger: Arc<dyn Logger>,
    timeout: Duration,
    closed: Arc<AtomicBool>,
}

impl NotificationClient {
    /// Initializes a NotificationClient pointing to a specific target address.
    pub fn new(target_addr: &str, logger: Option<Arc<dyn Logger>>) -> Self {
        Self {
            target_addr: target_addr.to_string(),
            logger: ensure_safe_logger(logger),
            timeout: DEFAULT_TIMEOUT,
            closed: Arc::new(AtomicBool::new(false)),
        }
    }

    // -----------------------------------------------------------------------------

    /// Initializes a NotificationClient by dynamically resolving the notif_server
    /// capability address from the provided ecosystem AppConfig.
    /// Fails fast if the notif_server capability or its gRPC address is unresolvable.
    pub fn from_config(app_config: &AppConfig, logger: Option<Arc<dyn Logger>>) -> Result<Self, String> {
        let safe_logger = ensure_safe_logger(logger);

        let addr = app_config
            .get_grpc_listen_addr("notif_server")
            .map_err(|e| format!("failed to resolve notif_server gRPC address: {}", e))?;

        if addr.trim().is_empty() {
            return Err("failed to resolve notif_server gRPC address: address is empty".to_string());
        }

        safe_logger.info(&format!("NotificationClient configured with target address: {}", addr));
        Ok(Self::new(&addr, Some(safe_logger)))
    }

    // -----------------------------------------------------------------------------

    /// Sets default RPC dispatch timeout.
    pub fn set_timeout(&mut self, timeout: Duration) {
        self.timeout = timeout;
    }

    // -----------------------------------------------------------------------------

    /// 1-line helper dispatching an untyped or informational notification
    /// with optional destination tags (e.g. "telegram", "discord").
    pub async fn send(&self, message: &str, tags: &[&str]) -> Result<(), String> {
        self.send_with_attachment("", message, "", tags).await
    }

    // -----------------------------------------------------------------------------

    /// Dispatches a categorized notification with a specific severity level
    /// (e.g., "TRADE", "CRITICAL", "WARNING", "REPORT", "INFO") and optional tags.
    pub async fn send_alert(&self, level: &str, message: &str, tags: &[&str]) -> Result<(), String> {
        self.send_with_attachment(level, message, "", tags).await
    }

    // -----------------------------------------------------------------------------

    /// Dispatches a full notification payload including level, message,
    /// attachment reference, and destination tags.
    pub async fn send_with_attachment(
        &self,
        level: &str,
        message: &str,
        attachment: &str,
        tags: &[&str],
    ) -> Result<(), String> {
        let client = self.clone();
        let level = level.to_string();
        let message = message.to_string();
        let attachment = attachment.to_string();
        let tags: Vec<String> = tags.iter().map(|s| s.to_string()).collect();

        tokio::task::spawn_blocking(move || {
            let tag_slices: Vec<&str> = tags.iter().map(|s| s.as_str()).collect();
            client.send_with_attachment_sync(&level, &message, &attachment, &tag_slices)
        })
        .await
        .map_err(|e| format!("join error: {}", e))?
    }

    // -----------------------------------------------------------------------------

    /// Synchronous helper dispatching an untyped notification.
    pub fn send_sync(&self, message: &str, tags: &[&str]) -> Result<(), String> {
        self.send_with_attachment_sync("", message, "", tags)
    }

    // -----------------------------------------------------------------------------

    /// Synchronous helper dispatching a categorized alert.
    pub fn send_alert_sync(&self, level: &str, message: &str, tags: &[&str]) -> Result<(), String> {
        self.send_with_attachment_sync(level, message, "", tags)
    }

    // -----------------------------------------------------------------------------

    /// Synchronous helper dispatching a notification over blocking libnotif bridge.
    pub fn send_with_attachment_sync(
        &self,
        level: &str,
        message: &str,
        attachment: &str,
        tags: &[&str],
    ) -> Result<(), String> {
        if self.closed.load(Ordering::SeqCst) {
            return Err("notification client is closed".to_string());
        }

        let lib = ffi::get_lib().ok_or_else(|| "failed to load libnotif dynamic library".to_string())?;

        let target_c = CString::new(self.target_addr.as_str()).map_err(|e| e.to_string())?;
        let level_c = CString::new(level).map_err(|e| e.to_string())?;
        let message_c = CString::new(message).map_err(|e| e.to_string())?;
        let attachment_c = CString::new(attachment).map_err(|e| e.to_string())?;
        let tags_csv = tags.join(",");
        let tags_c = CString::new(tags_csv).map_err(|e| e.to_string())?;

        let rc = (lib.notif_send_with_timeout)(
            target_c.as_ptr(),
            level_c.as_ptr(),
            message_c.as_ptr(),
            attachment_c.as_ptr(),
            tags_c.as_ptr(),
            self.timeout.as_secs_f64(),
        );

        if rc != 0 {
            let err_msg = unsafe {
                let ptr = (lib.notif_get_last_error)();
                if !ptr.is_null() {
                    let msg = CStr::from_ptr(ptr).to_string_lossy().into_owned();
                    (lib.notif_free_string)(ptr as *mut c_char);
                    msg
                } else {
                    format!("unknown error (rc={})", rc)
                }
            };
            self.logger.warning(&format!(
                "Notification dispatch to {} failed: {}",
                self.target_addr, err_msg
            ));
            return Err(format!("SendNotification failed (rc={}): {}", rc, err_msg));
        }

        self.logger.debug(&format!(
            "Notification dispatched successfully to {} (level={}, tags={:?})",
            self.target_addr, level, tags
        ));
        Ok(())
    }

    // -----------------------------------------------------------------------------

    /// Closes active notification client.
    pub fn close(&self) {
        self.closed.store(true, Ordering::SeqCst);
    }
}
