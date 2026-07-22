use std::process::Command;
use std::sync::OnceLock;

/// Get system hostname (cached)
pub fn get_hostname() -> &'static str {
    static HOSTNAME: OnceLock<String> = OnceLock::new();
    HOSTNAME.get_or_init(|| {
        Command::new("hostname")
            .output()
            .ok()
            .and_then(|output| {
                if output.status.success() {
                    Some(String::from_utf8_lossy(&output.stdout).trim().to_string())
                } else {
                    None
                }
            })
            .unwrap_or_else(|| "localhost".to_string())
    })
}

/// Returns the absolute path to the directory containing the current executable.
/// Provides a stable anchor for logs and config files, similar to the Go/Python implementations.
pub fn get_base_dir() -> String {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            return dir.to_string_lossy().to_string();
        }
    }
    ".".to_string()
}
