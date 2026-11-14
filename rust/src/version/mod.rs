// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized dynamic version resolution for Rust microservices and crates.
// Adheres to VERSION.txt as the ecosystem Single Source of Truth with caching.
//
// DATA FLOW:
// Hints / Tree Climber (VERSION.txt) -> Compile-time option_env!("APP_VERSION") (from build.rs VERSION.txt) -> Cache -> Panic (FAIL-FAST)
//
// KEY PARAMETERS:
// - get_version(): Returns and caches the resolved semantic version string.
// - resolve_version() / try_resolve_version(): Perform uncached hierarchical resolution (fail-fast).
// - set_version() / reset_version(): Cache override and invalidation helpers.
// - setup_version(): Build-script helper for build.rs execution.
// -----------------------------------------------------------------------------

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{OnceLock, RwLock};

static CACHED_VERSION: OnceLock<RwLock<Option<String>>> = OnceLock::new();

fn version_cache() -> &'static RwLock<Option<String>> {
    CACHED_VERSION.get_or_init(|| RwLock::new(None))
}

// -----------------------------------------------------------------------------

/// Returns the cached semantic version for the running microservice, resolving on first call.
/// Panics fail-fast if VERSION.txt and environment overrides are all absent.
pub fn get_version() -> String {
    if let Ok(guard) = version_cache().read() {
        if let Some(ref v) = *guard {
            return v.clone();
        }
    }

    let resolved = resolve_version();
    if let Ok(mut guard) = version_cache().write() {
        if let Some(ref existing) = *guard {
            return existing.clone();
        }
        *guard = Some(resolved.clone());
    }
    resolved
}

// -----------------------------------------------------------------------------

/// Performs hierarchical semver resolution without reading or mutating the cache.
/// Panics fail-fast if unresolved.
pub fn resolve_version() -> String {
    try_resolve_version().unwrap_or_else(|e| panic!("{}", e))
}

/// Performs hierarchical semver resolution with optional explicit candidate paths.
/// Panics fail-fast if unresolved.
pub fn resolve_version_with_hints(hints: &[&str]) -> String {
    try_resolve_version_with_hints(hints).unwrap_or_else(|e| panic!("{}", e))
}

/// Non-panicking hierarchical semver resolution returning Err if VERSION.txt and env overrides are absent.
pub fn try_resolve_version() -> Result<String, String> {
    try_resolve_version_with_hints(&[])
}

/// Non-panicking resolution scoped strictly to a specific starting directory (VERSION.txt only).
pub fn try_resolve_version_in_dir(dir: &Path) -> Result<String, String> {
    if let Some(v) = climb_dir_for_version(dir.to_path_buf()) {
        return Ok(v);
    }
    if let Some(v) = compile_time_version() {
        return Ok(v);
    }
    Err(format!(
        "version::resolve_version: VERSION.txt not found from '{}' (FAIL-FAST)",
        dir.display()
    ))
}

/// Non-panicking hierarchical semver resolution with optional explicit candidate paths.
pub fn try_resolve_version_with_hints(hints: &[&str]) -> Result<String, String> {
    // 1. Explicit candidate paths or starting directories
    for hint in hints {
        let trimmed_hint = hint.trim();
        if trimmed_hint.is_empty() {
            continue;
        }
        let p = Path::new(trimmed_hint);
        if p.is_file() {
            if let Some(v) = read_version_file(p) {
                return Ok(v);
            }
        } else if p.is_dir() {
            if let Some(v) = climb_dir_for_version(p.to_path_buf()) {
                return Ok(v);
            }
        }
    }

    // 2. Upward directory climber starting from cwd and current_exe parent
    if let Some(v) = climb_for_version() {
        return Ok(v);
    }

    // 3. Compile-time VERSION.txt baked via build.rs setup_version()
    if let Some(v) = compile_time_version() {
        return Ok(v);
    }

    Err("version::resolve_version: VERSION.txt not found or empty (FAIL-FAST)".to_string())
}

// -----------------------------------------------------------------------------

/// Explicitly sets the cached version. Panics fail-fast on empty/whitespace values.
pub fn set_version(version: &str) {
    let trimmed = version.trim();
    if trimmed.is_empty() {
        panic!("version::set_version: version string must not be empty (FAIL-FAST)");
    }
    if let Ok(mut guard) = version_cache().write() {
        *guard = Some(trimmed.to_string());
    }
}

/// Clears the cached version so the next `get_version()` re-resolves.
pub fn reset_version() {
    if let Ok(mut guard) = version_cache().write() {
        *guard = None;
    }
}

// -----------------------------------------------------------------------------

/// Build-script helper intended to be called inside `build.rs`.
/// Emits `cargo:rustc-env=APP_VERSION=<version>` and `cargo:rerun-if-changed`, failing fast if absent.
pub fn setup_version() {
    let version = try_resolve_version().unwrap_or_else(|e| panic!("{}", e));
    println!("cargo:rustc-env=APP_VERSION={}", version.trim());
    println!("cargo:rerun-if-changed=VERSION.txt");
    println!("cargo:rerun-if-changed=../VERSION.txt");
}

fn compile_time_version() -> Option<String> {
    if let Some(v) = option_env!("APP_VERSION") {
        let trimmed = v.trim();
        if !trimmed.is_empty() {
            return Some(trimmed.to_string());
        }
    }
    None
}

// -----------------------------------------------------------------------------

fn read_version_file(path: &Path) -> Option<String> {
    if !path.is_file() {
        return None;
    }
    let content = fs::read_to_string(path).ok()?;
    let trimmed = content.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn climb_dir_for_version(start_dir: PathBuf) -> Option<String> {
    let mut curr = start_dir;
    for _ in 0..12 {
        let candidate = curr.join("VERSION.txt");
        if let Some(v) = read_version_file(&candidate) {
            return Some(v);
        }

        if curr.join(".git").exists() {
            break;
        }

        match curr.parent() {
            Some(p) if p != curr => curr = p.to_path_buf(),
            _ => break,
        }
    }
    None
}

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
        if let Some(v) = climb_dir_for_version(start_dir) {
            return Some(v);
        }
    }

    None
}
