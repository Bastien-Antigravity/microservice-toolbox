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
        let is_docker = Path::new("/.dockerenv").exists() || env::var("DOCKER_ENV").unwrap_or_default() == "true";
        Self { is_docker }
    }

    /// Resolves the requested IP into an actual address to bind to.
    /// If in Docker, it ignores loopback requests and finds the container's primary IP.
    pub fn resolve_bind_addr(&self, requested_ip: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let requested_ip = requested_ip.trim_matches('"');

        // If not in Docker, or if the IP isn't a loopback placeholder, use it directly.
        if !self.is_docker || !self.is_loopback(requested_ip) {
            return Ok(requested_ip.to_string());
        }

        // In Docker, we need the internal container IP (e.g., eth0) for other containers to reach us.
        self.get_primary_interface_ip()
    }

    /// Checks if the IP is in the 127.0.0.0/8 range or localhost.
    pub fn is_loopback(&self, ip: &str) -> bool {
        ip.starts_with("127.") || ip == "::1" || ip.to_lowercase() == "localhost"
    }

    /// Finds the first non-loopback IP address using a UDP socket trick.
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
