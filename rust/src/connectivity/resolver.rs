use std::env;
use std::path::Path;
use std::net::UdpSocket;

/// Resolver handles environment-aware network address translation.
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
    /// Resolves the requested IP into an actual address to bind to.
    /// 
    /// Docker Guard Logic:
    /// If running in a Docker container, this method suppresses the requested IP
    /// and forces a bind to 0.0.0.0. This ensures that the container port mapping
    /// (Docker/K8s) works regardless of what was specified in the configuration.
    pub fn resolve_bind_addr(&self, requested_ip: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let requested_ip = requested_ip.trim_matches('"');

        // If not in Docker, use the requested IP directly.
        if !self.is_docker {
            return Ok(requested_ip.to_string());
        }

        // In Docker, we force 0.0.0.0 to ensure orchestrated networking works.
        // This "suppresses" any manual IP overrides.
        Ok("0.0.0.0".to_string())
    }

    /// Takes a "host:port" string and returns a resolved "host:port"
    /// using the Docker Guard logic.
    pub fn resolve_full_bind_addr(&self, addr: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        if !addr.contains(':') {
            return self.resolve_bind_addr(addr);
        }

        let parts: Vec<&str> = addr.rsplitn(2, ':').collect();
        if parts.len() != 2 {
            return self.resolve_bind_addr(addr);
        }

        let port = parts[0];
        let host = parts[1];
        let resolved_host = self.resolve_bind_addr(host)?;
        Ok(format!("{}:{}", resolved_host, port))
    }

    /// Checks if the IP is in the 127.0.0.0/8 range or localhost.
    pub fn is_loopback(&self, ip: &str) -> bool {
        ip.starts_with("127.") || ip == "::1" || ip.to_lowercase() == "localhost"
    }

    /// Finds the first non-loopback IP address using a UDP socket trick.
    /// Keep as utility for potential client-side discovery.
    pub fn get_primary_interface_ip(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // UDP socket trick to find the primary outgoing interface IP
        let socket = UdpSocket::bind("0.0.0.0:0")?;
        socket.connect("10.255.255.255:1")?;
        let addr = socket.local_addr()?;
        let ip = addr.ip().to_string();
        
        if !self.is_loopback(&ip) {
            return Ok(ip);
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
    fn test_resolve_bind_addr_native() {
        let r = Resolver { is_docker: false };
        assert_eq!(r.resolve_bind_addr("127.0.0.1").unwrap(), "127.0.0.1");
        assert_eq!(r.resolve_bind_addr("8.8.8.8").unwrap(), "8.8.8.8");
    }

    #[test]
    fn test_resolve_bind_addr_docker_suppression() {
        let r = Resolver { is_docker: true };
        assert_eq!(r.resolve_bind_addr("127.0.0.1").unwrap(), "0.0.0.0");
        assert_eq!(r.resolve_bind_addr("8.8.8.8").unwrap(), "0.0.0.0");
    }

    #[test]
    fn test_resolve_full_bind_addr() {
        let r = Resolver { is_docker: true };
        assert_eq!(r.resolve_full_bind_addr("127.0.0.1:50051").unwrap(), "0.0.0.0:50051");
        assert_eq!(r.resolve_full_bind_addr("8.8.8.8:8080").unwrap(), "0.0.0.0:8080");
    }
}
