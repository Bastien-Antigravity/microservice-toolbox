use serde_yaml::Value;
use std::fs;
use crate::config::args::ToolboxArgs;

pub struct AppConfig {
    pub profile: String,
    pub data: Value,
    pub cli_args: ToolboxArgs,
}

impl AppConfig {
    pub fn load(profile: &str) -> Self {
        let mut ac = AppConfig {
            profile: profile.to_string(),
            data: Value::Mapping(serde_yaml::Mapping::new()),
            cli_args: ToolboxArgs::parse(),
        };

        // Priority Logic:
        // 1. Env (Base) & 2. Server (Placeholder)
        // ... (Future: Sync with Server)

        // 3. Local File
        let is_dev = profile == "standalone" || profile == "test";
        if is_dev {
            println!("Toolbox (Rust): Dev Mode. File > Server.");
            ac.load_from_file(&format!("{}.yaml", profile));
        } else {
            println!("Toolbox (Rust): Production Mode. Server > File.");
            // Logic for Server > File would go here
            ac.load_from_file(&format!("{}.yaml", profile));
        }

        // 4. CLI Overrides
        ac.apply_cli_overrides();

        ac
    }

    fn load_from_file(&mut self, filename: &str) {
        if let Ok(content) = fs::read_to_string(filename) {
            if let Ok(file_data) = serde_yaml::from_str::<Value>(&content) {
                Self::deep_merge_values(&mut self.data, &file_data);
            }
        }
    }

    fn apply_cli_overrides(&mut self) {
        if let Some(name) = &self.cli_args.name {
            self.set_value("common.name", Value::String(name.clone()));
        }

        if self.cli_args.host.is_some() || self.cli_args.port.is_some() {
            let target = self.cli_args.name.as_deref().unwrap_or("config_server").to_string();
            
            if let Some(host) = &self.cli_args.host {
                self.set_value(&format!("capabilities.{}.ip", target), Value::String(host.clone()));
            }
            if let Some(port) = &self.cli_args.port {
                self.set_value(&format!("capabilities.{}.port", target), Value::String(port.to_string()));
            }
        }
    }

    fn deep_merge_values(dst: &mut Value, src: &Value) {
        if let (Some(dst_map), Some(src_map)) = (dst.as_mapping_mut(), src.as_mapping()) {
            for (k, v) in src_map {
                if !dst_map.contains_key(k) || !v.is_mapping() {
                    dst_map.insert(k.clone(), v.clone());
                } else {
                    Self::deep_merge_values(dst_map.get_mut(k).unwrap(), v);
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
}
