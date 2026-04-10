use serde_yaml::Value;
use std::fs;
use crate::config::args::ToolboxArgs;

pub struct AppConfig {
    pub profile: String,
    pub data: Value,
    pub cli_args: ToolboxArgs,
}

pub fn load_config(profile: &str) -> AppConfig {
    AppConfig::load_config(profile)
}

impl AppConfig {
    pub fn load_config(profile: &str) -> Self {
        let mut ac = AppConfig {
            profile: profile.to_string(),
            data: Value::Mapping(serde_yaml::Mapping::new()),
            cli_args: ToolboxArgs::parse_cli_args(),
        };

        // Priority Logic:
        let is_dev = profile == "standalone" || profile == "test";
        if is_dev {
            println!("Toolbox (Rust): Dev Mode. File > Server.");
            ac.load_from_file(&format!("{}.yaml", profile));
        } else {
            println!("Toolbox (Rust): Production Mode. Server > File.");
            ac.load_from_file(&format!("{}.yaml", profile));
        }

        ac.apply_cli_overrides();
        ac
    }

    fn load_from_file(&mut self, filename: &str) {
        if let Ok(content) = fs::read_to_string(filename) {
            if let Ok(file_data) = serde_yaml::from_str::<Value>(&content) {
                Self::deep_merge(&mut self.data, &file_data);
            }
        }
    }

    fn apply_cli_overrides(&mut self) {
        if let Some(name) = &self.cli_args.name {
            self.set_value("common.name", Value::String(name.clone()));
        }

        if self.cli_args.host.is_some() || self.cli_args.port.is_some() || self.cli_args.grpc_host.is_some() || self.cli_args.grpc_port.is_some() {
            let target = self.cli_args.name.as_deref().unwrap_or("config_server").to_string();
            
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

    pub fn get_listen_addr(&self, name: &str) -> String {
        self.get_addr(name, "ip", "port")
    }

    pub fn get_grpc_listen_addr(&self, name: &str) -> String {
        let ip = self
            .get_value(&format!("capabilities.{}.grpc_ip", name))
            .and_then(|v| v.as_str())
            .or_else(|| {
                self.get_value(&format!("capabilities.{}.ip", name))
                    .and_then(|v| v.as_str())
            })
            .unwrap_or("127.0.0.1");

        let port_val = self
            .get_value(&format!("capabilities.{}.grpc_port", name))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string())
            .or_else(|| {
                self.get_value(&format!("capabilities.{}.port", name))
                    .and_then(|v| v.as_str())
                    .map(|s| {
                        let p = s.parse::<u16>().unwrap_or(80);
                        (p + 1).to_string()
                    })
            })
            .unwrap_or_else(|| "81".to_string());

        format!("{}:{}", ip, port_val)
    }

    fn get_addr(&self, name: &str, host_key: &str, port_key: &str) -> String {
        let ip = self.get_value(&format!("capabilities.{}.{}", name, host_key))
            .and_then(|v| v.as_str())
            .unwrap_or("127.0.0.1");
        let port = self.get_value(&format!("capabilities.{}.{}", name, port_key))
            .and_then(|v| v.as_str())
            .unwrap_or("80");
        format!("{}:{}", ip, port)
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
                    map.insert(Value::String(part.to_string()), Value::Mapping(serde_yaml::Mapping::new()));
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
