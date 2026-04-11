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
