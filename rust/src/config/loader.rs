use serde_yml::Value;
use std::fs;
use std::sync::Arc;
use crate::config::args::ToolboxArgs;
use crate::utils::logger::{Logger, ensure_safe_logger};

#[cfg(feature = "unilog")]
use crate::utils::logger::UniLogger;

#[cfg(feature = "unilog")]
use unilog_rs::LogLevel;

pub struct AppConfig {
    pub profile: String,
    pub data: Value,
    pub cli_args: ToolboxArgs,
    pub logger: Arc<dyn Logger>,
}

pub fn load_config(profile: &str) -> Result<AppConfig, Box<dyn std::error::Error>> {
    AppConfig::load_config(profile, None)
}

pub fn load_config_with_logger(profile: &str, logger: Option<Arc<dyn Logger>>) -> Result<AppConfig, Box<dyn std::error::Error>> {
    AppConfig::load_config(profile, logger)
}

impl AppConfig {
    pub fn load_config(profile: &str, logger: Option<Arc<dyn Logger>>) -> Result<Self, Box<dyn std::error::Error>> {
        let cli_args = ToolboxArgs::parse_cli_args();
        
        // If no logger provided, try to bootstrap UniLogger if enabled, else default
        let final_logger = match logger {
            Some(l) => l,
            None => {
                #[cfg(feature = "unilog")]
                {
                    let app_name = cli_args.name.as_deref().unwrap_or("rust-app");
                    match unilog_rs::UniLog::new(profile, app_name, "standard", LogLevel::Info, false) {
                        Ok(unilog) => Arc::new(UniLogger::new(unilog)),
                        Err(e) => {
                            let fallback = ensure_safe_logger(None);
                            fallback.warning(&format!("Failed to bootstrap UniLogger: {}. Falling back to default.", e));
                            fallback
                        }
                    }
                }
                #[cfg(not(feature = "unilog"))]
                {
                    ensure_safe_logger(None)
                }
            }
        };

        let mut ac = AppConfig {
            profile: profile.to_string(),
            data: Value::Mapping(serde_yml::Mapping::new()),
            cli_args,
            logger: final_logger,
        };

        // Phase 1: Load base config from file (full merge of all sections)
        ac.load_from_file(&format!("{}.yaml", profile));

        // Phase 2: Layered logic matching Go implementation
        let is_dev = profile == "standalone" || profile == "test";
        if is_dev {
            ac.logger.info("Dev Mode detected. Re-applying Local File as Hard Override.");
            // Re-apply file capabilities as hard override (matching Go applyFileOverride)
            ac.apply_file_override(&format!("{}.yaml", profile));
        } else {
            ac.logger.info("Production Mode detected. Config Server remains authoritative.");
        }

        ac.apply_cli_overrides();
        Ok(ac)
    }

    /// Full merge of all file data into self.data
    fn load_from_file(&mut self, filename: &str) {
        if let Ok(content) = fs::read_to_string(filename) {
            if let Ok(file_data) = serde_yml::from_str::<Value>(&content) {
                Self::deep_merge(&mut self.data, &file_data);
            }
        }
    }

    /// Re-reads a file and merges ONLY the capabilities section as a hard override.
    /// This matches Go's applyFileOverride behavior.
    fn apply_file_override(&mut self, filename: &str) {
        if let Ok(content) = fs::read_to_string(filename) {
            if let Ok(file_data) = serde_yml::from_str::<Value>(&content) {
                if let Some(caps) = file_data.get("capabilities") {
                    if self.data.get("capabilities").is_none() {
                        self.set_value("capabilities", Value::Mapping(serde_yml::Mapping::new()));
                    }
                    if let Some(dst_caps) = self.data.get_mut("capabilities") {
                        Self::deep_merge(dst_caps, caps);
                    }
                }
            }
        }
    }


    fn apply_cli_overrides(&mut self) {
        if let Some(name) = &self.cli_args.name {
            self.set_value("common.name", Value::String(name.clone()));
        }

        if self.cli_args.host.is_some() || self.cli_args.port.is_some() || self.cli_args.grpc_host.is_some() || self.cli_args.grpc_port.is_some() {
            let config_name = self.get_value("common.name").and_then(|v| v.as_str()).map(String::from);
            let target = self.cli_args.name.clone().or(config_name).unwrap_or_else(|| "config_server".to_string());
            
            if let Some(host) = &self.cli_args.host {
                self.set_value(&format!("capabilities.{}.ip", target), Value::String(host.clone()));
            }
            if let Some(port) = &self.cli_args.port {
                self.set_value(&format!("capabilities.{}.port", target), Value::String(port.to_string()));
            }
            if let Some(grpc_host) = &self.cli_args.grpc_host {
                self.set_value(&format!("capabilities.{}.grpc_ip", target), Value::String(grpc_host.clone()));
            }
            if let Some(grpc_port) = &self.cli_args.grpc_port {
                self.set_value(&format!("capabilities.{}.grpc_port", target), Value::String(grpc_port.to_string()));
            }
        }
    }

    pub fn get_listen_addr(&self, capability: &str) -> Result<String, String> {
        self.get_addr(capability, "ip", "port")
    }

    pub fn get_grpc_listen_addr(&self, capability: &str) -> Result<String, String> {
        // 1. Try explicit grpc config
        if let Ok(addr) = self.get_addr(capability, "grpc_ip", "grpc_port") {
            return Ok(addr);
        }

        // 2. Fallback to convention: ip:port+1 (matching Go implementation)
        let cap_path = format!("capabilities.{}", capability);
        let cap = self.get_value(&cap_path).ok_or_else(|| format!("capability {} not found for gRPC fallback", capability))?;

        let host = cap.get("ip")
            .and_then(|v| v.as_str())
            .unwrap_or("0.0.0.0");

        let port_str = cap.get("port")
            .and_then(|v| v.as_str())
            .unwrap_or("8080");

        let port = port_str.parse::<u16>().unwrap_or(8080);
        Ok(format!("{}:{}", host, port + 1))
    }

    fn get_addr(&self, capability: &str, host_key: &str, port_key: &str) -> Result<String, String> {
        let cap_path = format!("capabilities.{}", capability);
        let cap = self.get_value(&cap_path).ok_or_else(|| format!("capability {} not found", capability))?;

        let host = cap.get(host_key)
            .and_then(|v| v.as_str())
            .unwrap_or("0.0.0.0");

        let port = cap.get(port_key)
            .and_then(|v| v.as_str())
            .ok_or_else(|| format!("port key {} missing or empty in capability {}", port_key, capability))?;

        Ok(format!("{}:{}", host, port))
    }

    pub fn deep_merge(dst: &mut Value, src: &Value) {
        if let (Some(dst_map), Some(src_map)) = (dst.as_mapping_mut(), src.as_mapping()) {
            for (k, v) in src_map {
                if !dst_map.contains_key(k) || !v.is_mapping() {
                    dst_map.insert(k.clone(), v.clone());
                } else {
                    Self::deep_merge(dst_map.get_mut(k).unwrap(), v);
                }
            }
        } else {
            *dst = src.clone();
        }
    }

    fn set_value(&mut self, path: &str, val: Value) {
        let mut current = &mut self.data;
        let parts: Vec<&str> = path.split('.').collect();
        for (i, part) in parts.iter().enumerate() {
            if i == parts.len() - 1 {
                if let Some(map) = current.as_mapping_mut() {
                    map.insert(Value::String(part.to_string()), val);
                }
                return;
            }
            if !current.as_mapping().map_or(false, |m| m.contains_key(&Value::String(part.to_string()))) {
                if let Some(map) = current.as_mapping_mut() {
                    map.insert(Value::String(part.to_string()), Value::Mapping(serde_yml::Mapping::new()));
                }
            }
            current = current.as_mapping_mut().unwrap().get_mut(&Value::String(part.to_string())).unwrap();
        }
    }

    fn get_value(&self, path: &str) -> Option<&Value> {
        let mut current = &self.data;
        for part in path.split('.') {
            if let Some(map) = current.as_mapping() {
                current = map.get(&Value::String(part.to_string()))?;
            } else {
                return None;
            }
        }
        Some(current)
    }
}
