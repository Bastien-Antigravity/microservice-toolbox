// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Resolves configured capability network addresses strictly from AppConfig inputs.
//
// DATA FLOW:
// Config Address Input -> Validation + Host/Port Split -> Final Bind Address
//
// KEY PARAMETERS:
// - requested_ip: Configured bind IP/host (zero hardcoded defaults).
// -----------------------------------------------------------------------------

use std::env;
use std::net::ToSocketAddrs;
use std::path::Path;

/// Resolver handles config-driven network address resolution with zero hardcoded defaults.
pub struct Resolver {
    pub is_docker: bool,
}

impl Resolver {
    /// Creates a new network resolver.
    pub fn new() -> Self {
        let is_docker = Path::new("/.dockerenv").exists() || env::var("DOCKER_ENV").is_ok_and(|v| v == "true");
        Self { is_docker }
    }
}

impl Default for Resolver {
    fn default() -> Self {
        Self::new()
    }
}

impl Resolver {
    /// Validates and returns the configured IP directly (fail-fast if empty, no hardcoded fallback).
    pub fn resolve_bind_addr(&self, requested_ip: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        if requested_ip.trim().is_empty() {
            return Err("Resolver::resolve_bind_addr: configured bind IP must not be empty (FAIL-FAST)".into());
        }
        Ok(requested_ip.to_string())
    }

    /// Validates and returns a configured "host:port", "[ipv6]:port", or bare host string.
    pub fn resolve_full_bind_addr(&self, addr: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        if addr.trim().is_empty() {
            return Err("Resolver::resolve_full_bind_addr: configured bind address must not be empty (FAIL-FAST)".into());
        }

        if addr.starts_with('[') {
            if let Some(idx) = addr.rfind("]:") {
                let host = &addr[1..idx];
                let port = &addr[idx + 2..];
                if port.trim().is_empty() {
                    return Err("Resolver::resolve_full_bind_addr: configured port must not be empty (FAIL-FAST)".into());
                }
                let resolved_host = self.resolve_bind_addr(host)?;
                if resolved_host.contains(':') {
                    return Ok(format!("[{}]:{}", resolved_host, port));
                }
                return Ok(format!("{}:{}", resolved_host, port));
            }
            return self.resolve_bind_addr(addr);
        }

        if addr.matches(':').count() == 1 {
            if let Some((host, port)) = addr.split_once(':') {
                if port.trim().is_empty() {
                    return Err("Resolver::resolve_full_bind_addr: configured port must not be empty (FAIL-FAST)".into());
                }
                let resolved_host = self.resolve_bind_addr(host)?;
                return Ok(format!("{}:{}", resolved_host, port));
            }
        }

        self.resolve_bind_addr(addr)
    }

    /// Returns whether the resolver detected a Docker container environment.
    pub fn is_docker_env(&self) -> bool {
        self.is_docker
    }

    /// Checks if the IP is in the 127.0.0.0/8 range or localhost.
    pub fn is_loopback(&self, ip: &str) -> bool {
        ip.starts_with("127.") || ip == "::1" || ip.to_lowercase() == "localhost"
    }

    /// Finds the first non-loopback IPv4 address for the local hostname without hardcoded probe IPs.
    pub fn get_primary_interface_ip(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        #[cfg(unix)]
        {
            unsafe extern "C" {
                fn gethostname(name: *mut std::os::raw::c_char, len: usize) -> std::os::raw::c_int;
            }
            let mut buf = [0u8; 256];
            if unsafe { gethostname(buf.as_mut_ptr() as *mut std::os::raw::c_char, buf.len()) } == 0 {
                let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
                if let Ok(hostname) = std::str::from_utf8(&buf[..end]) {
                    let target = format!("{}:0", hostname.trim());
                    if let Ok(addrs) = target.to_socket_addrs() {
                        for addr in addrs {
                            if let std::net::IpAddr::V4(v4) = addr.ip() {
                                let ip = v4.to_string();
                                if !self.is_loopback(&ip) {
                                    return Ok(ip);
                                }
                            }
                        }
                    }
                }
            }
        }

        Err("no primary network interface found".into())
    }
}

pub fn new_resolver() -> Resolver {
    Resolver::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_loopback() {
        let r = Resolver { is_docker: false };
        assert!(r.is_loopback("127.0.0.1"));
        assert!(r.is_loopback("127.2.3.4"));
        assert!(r.is_loopback("::1"));
        assert!(r.is_loopback("localhost"));
        assert!(!r.is_loopback("8.8.8.8"));
    }

    #[test]
    fn test_resolve_bind_addr_preserves_config() {
        let r = Resolver { is_docker: false };
        assert_eq!(r.resolve_bind_addr("127.0.0.1").unwrap(), "127.0.0.1");
        assert_eq!(r.resolve_bind_addr("8.8.8.8").unwrap(), "8.8.8.8");

        let r_docker = Resolver { is_docker: true };
        assert_eq!(r_docker.resolve_bind_addr("10.1.2.3").unwrap(), "10.1.2.3");
        assert!(r_docker.resolve_bind_addr("").is_err());
    }

    #[test]
    fn test_resolve_full_bind_addr() {
        let r = Resolver { is_docker: true };
        assert_eq!(r.resolve_full_bind_addr("127.0.0.1:50051").unwrap(), "127.0.0.1:50051");
        assert_eq!(r.resolve_full_bind_addr("[::1]:8080").unwrap(), "[::1]:8080");
        assert_eq!(r.resolve_full_bind_addr("::1").unwrap(), "::1");
        assert!(r.resolve_full_bind_addr(":50051").is_err());
        assert!(r.resolve_full_bind_addr("127.0.0.1:").is_err());
    }
}
