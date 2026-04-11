use crate::utils::helpers::get_hostname;
use chrono::Local;

/// Formats and prints an internal toolbox log message
pub fn print_internal_log(
    level: &str,
    module: &str,
    filename: &str,
    line: &str,
    message: &str,
) {
    let timestamp = Local::now().format("%Y-%m-%dT%H:%M:%S%.9fZ").to_string();
    let hostname = get_hostname();
    
    // Colorize level
    let colored_level = match level {
        "DEBUG" => format!("\x1b[36m{:<10}\x1b[0m", truncate(level, 10)),
        "INFO" | "LOGON" | "LOGOUT" => format!("\x1b[32m{:<10}\x1b[0m", truncate(level, 10)),
        "WARNING" => format!("\x1b[33m{:<10}\x1b[0m", truncate(level, 10)),
        "ERROR" | "CRITICAL" => format!("\x1b[31m{:<10}\x1b[0m", truncate(level, 10)),
        _ => format!("{:<10}", truncate(level, 10)),
    };

    // Fixed column format: 33-12-15-10-20-25-6 message
    println!(
        "{:<33} {:<12} {:<22} {:<10} {:<20} {:<25} {:<6} {}",
        timestamp,
        truncate(hostname, 12),
        truncate("microservice-toolbox", 22),
        colored_level,
        truncate(filename, 20),
        truncate(module, 25),
        truncate(line, 6),
        message
    );
}

fn truncate(s: &str, max_len: usize) -> &str {
    if s.len() > max_len {
        &s[..max_len]
    } else {
        s
    }
}
