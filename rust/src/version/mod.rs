// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized dynamic version resolution for Rust microservices and crates.
// Adheres to VERSION.txt as the ecosystem Single Source of Truth.
//
// DATA FLOW:
// Compile-time option_env!("APP_VERSION") -> Runtime Env -> Directory Climber (VERSION.txt) -> Fallback (0.0.1)
//
// KEY PARAMETERS:
// - get_version(): Returns the dynamic semantic version string.
// - setup_version(): Build-time helper for build.rs execution.
// -----------------------------------------------------------------------------

use std::fs;
use std::path::PathBuf;

pub const DEFAULT_FALLBACK_VERSION: &str = "0.0.1";

// -----------------------------------------------------------------------------

/// Returns the resolved semantic version for the running microservice.
pub fn get_version() -> String {
    // 1. Compile-time environment variable injected via build.rs
    if let Some(v) = option_env!("APP_VERSION") {
        let trimmed = v.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }

    // 2. Runtime environment variables
    for key in &["APP_VERSION", "SERVICE_VERSION"] {
        if let Ok(val) = std::env::var(key) {
            let trimmed = val.trim().to_string();
            if !trimmed.is_empty() {
                return trimmed;
            }
        }
    }

    // 3. Upward directory climber looking for VERSION.txt
    if let Some(v) = climb_for_version() {
        return v;
    }

    // 4. Default fallback
    DEFAULT_FALLBACK_VERSION.to_string()
}

// -----------------------------------------------------------------------------

/// Build-script helper intended to be called inside `build.rs`.
/// Emits `cargo:rustc-env=APP_VERSION=<version>` and `cargo:rerun-if-changed`.
pub fn setup_version() {
    let version = climb_for_version().unwrap_or_else(|| DEFAULT_FALLBACK_VERSION.to_string());
    println!("cargo:rustc-env=APP_VERSION={}", version.trim());
    println!("cargo:rerun-if-changed=VERSION.txt");
    println!("cargo:rerun-if-changed=../VERSION.txt");
}

// -----------------------------------------------------------------------------

fn climb_for_version() -> Option<String> {
    let mut search_dirs = Vec::new();

    if let Ok(cwd) = std::env::current_dir() {
        search_dirs.push(cwd);
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            search_dirs.push(parent.to_path_buf());
        }
    }

    for start_dir in search_dirs {
        let mut curr: PathBuf = start_dir;
        for _ in 0..12 {
            let candidate = curr.join("VERSION.txt");
            if candidate.is_file() {
                if let Ok(content) = fs::read_to_string(&candidate) {
                    let trimmed = content.trim();
                    if !trimmed.is_empty() {
                        return Some(trimmed.to_string());
                    }
                }
            }

            if curr.join(".git").exists() {
                break;
            }

            match curr.parent() {
                Some(p) if p != curr => curr = p.to_path_buf(),
                _ => break,
            }
        }
    }

    None
}
