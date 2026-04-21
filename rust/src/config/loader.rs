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

/// Initializes a configuration loader following the Microservice Toolbox 'Hierarchy of Truth'.
/// 
/// Priority levels (highest to lowest):
/// 1. CLI Overrides (e.g., --host, --port)
/// 2. Context-Aware File Overrides (Dev Mode Hard Overrides)
/// 3. Production/Fleet Source (Config Server or YAML)
/// 4. Base environment/defaults
pub fn load_config(profile: &str) -> Result<AppConfig, Box<dyn std::error::Error>> {
    AppConfig::load_config(profile, None)
}

/// Semantic helper to match Go LoadConfigWithLogger().
pub fn load_config_with_logger(profile: &str, logger: Option<Arc<dyn Logger>>) -> Result<AppConfig, Box<dyn std::error::Error>> {
    AppConfig::load_config(profile, logger)
}

impl AppConfig {
    /// Loads and merges configuration data based on the provided profile.
    /// It automatically handles platform-specific overrides and CLI priority.
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
        if let Ok(content) = fs::read_to_string(filename)
            && let Ok(file_data) = serde_yml::from_str::<Value>(&content) {
                Self::deep_merge(&mut self.data, &file_data);
        }
    }

    /// Re-reads a file and merges ONLY the capabilities section as a hard override.
    /// This matches Go's applyFileOverride behavior.
    fn apply_file_override(&mut self, filename: &str) {
        if let Ok(content) = fs::read_to_string(filename)
            && let Ok(file_data) = serde_yml::from_str::<Value>(&content)
            && let Some(caps) = file_data.get("capabilities") {
                if self.data.get("capabilities").is_none() {
                    let _ = self.set_value("capabilities", Value::Mapping(serde_yml::Mapping::new()));
                }
                
                let current_caps = self.data.get_mut("capabilities").unwrap();
                if let Some(target_map) = current_caps.as_mapping_mut()
                    && let Some(source_map) = caps.as_mapping() {
                        for (k, v) in source_map {
                            target_map.insert(k.clone(), v.clone());
                        }
                }
        }
    }

    fn apply_cli_overrides(&mut self) {
        if let Some(name) = self.cli_args.name.clone() {
            let _ = self.set_value("common.name", Value::String(name));
        }

        if let Some(host) = self.cli_args.host.clone() {
            let port = self.cli_args.port;
            let grpc_host = self.cli_args.grpc_host.clone();
            let grpc_port = self.cli_args.grpc_port;

            for target in ["config", "log", "notif", "tele"] {
                let _ = self.set_value(&format!("capabilities.{}.ip", target), Value::String(host.clone()));
                if let Some(p) = port {
                    let _ = self.set_value(&format!("capabilities.{}.port", target), Value::String(p.to_string()));
                }
                if let Some(gh) = &grpc_host {
                    let _ = self.set_value(&format!("capabilities.{}.grpc_ip", target), Value::String(gh.clone()));
                }
                if let Some(gp) = grpc_port {
                    let _ = self.set_value(&format!("capabilities.{}.grpc_port", target), Value::String(gp.to_string()));
                }
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

    fn set_value(&mut self, path: &str, value: Value) -> Result<(), Box<dyn std::error::Error>> {
        let mut current = &mut self.data;
        let parts: Vec<&str> = path.split('.').collect();
        for (_i, part) in parts.iter().enumerate().take(parts.len() - 1) {
            if !current.as_mapping().is_some_and(|m| m.contains_key(Value::String(part.to_string())))
                && let Some(map) = current.as_mapping_mut() {
                    map.insert(Value::String(part.to_string()), Value::Mapping(serde_yml::Mapping::new()));
            }

            current = current.as_mapping_mut().unwrap().get_mut(Value::String(part.to_string())).unwrap();
        }

        if let Some(map) = current.as_mapping_mut() {
            map.insert(Value::String(parts.last().unwrap().to_string()), value);
        } else {
            return Err("Config path tail is not a mapping".into());
        }
        Ok(())
    }

    pub fn get_value(&self, path: &str) -> Option<&Value> {
        let parts: Vec<&str> = path.split('.').collect();
        let mut current = &self.data;

        for part in parts {
            if let Some(map) = current.as_mapping() {
                current = map.get(Value::String(part.to_string()))?;
            } else {
                return None;
            }
        }
        Some(current)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_yml;

    #[test]
    fn test_config_deep_merge() {
        let mut dst = serde_yml::from_str::<Value>("a: 1\nb:\n  c: 2").unwrap();
        let src = serde_yml::from_str::<Value>("b:\n  d: 3\ne: 4").unwrap();
        
        AppConfig::deep_merge(&mut dst, &src);
        
        assert_eq!(dst.get("a").unwrap().as_u64().unwrap(), 1);
        assert_eq!(dst.get("e").unwrap().as_u64().unwrap(), 4);
        assert_eq!(dst.get("b").unwrap().get("c").unwrap().as_u64().unwrap(), 2);
        assert_eq!(dst.get("b").unwrap().get("d").unwrap().as_u64().unwrap(), 3);
    }

    #[test]
    fn test_config_get_addr() {
        let ac = AppConfig {
            data: serde_yml::from_str::<Value>("capabilities:\n  test:\n    ip: 1.2.3.4\n    port: \"8080\"").unwrap(),
            profile: "test".to_string(),
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
        };
        
        assert_eq!(ac.get_listen_addr("test").unwrap(), "1.2.3.4:8080");
        assert_eq!(ac.get_grpc_listen_addr("test").unwrap(), "1.2.3.4:8081");
    }
}
