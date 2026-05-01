use serde_yml::Value;
use std::fs;
use std::ffi::{CStr, CString, c_char};
use std::sync::{Arc, Mutex, OnceLock};
use crate::config::args::ToolboxArgs;
use crate::config::merger::deep_merge;
use crate::utils::logger::{Logger, ensure_safe_logger};

#[cfg(feature = "unilog")]
use crate::utils::logger::UniLogger;

#[cfg(feature = "unilog")]
use unilog_rs::LogLevel;

// Static callback registry — routes C callbacks to Rust closures.
// One AppConfig per process is the standard microservice pattern.
type CbBox = Box<dyn Fn(serde_json::Value) + Send + Sync>;
static LIVE_CB: OnceLock<Mutex<Option<CbBox>>> = OnceLock::new();
static REG_CB: OnceLock<Mutex<Option<CbBox>>> = OnceLock::new();

fn get_live_cb() -> &'static Mutex<Option<CbBox>> {
    LIVE_CB.get_or_init(|| Mutex::new(None))
}
fn get_reg_cb() -> &'static Mutex<Option<CbBox>> {
    REG_CB.get_or_init(|| Mutex::new(None))
}

pub struct AppConfig {
    pub profile: String,
    pub data: Value,
    pub cli_args: ToolboxArgs,
    pub logger: Arc<dyn Logger>,
    _handle: Option<usize>,
    _live_cb: Option<Box<dyn Fn(serde_json::Value) + Send + Sync>>,
    _reg_cb: Option<Box<dyn Fn(serde_json::Value) + Send + Sync>>,
}

/// Initializes a configuration loader following the Microservice Toolbox 'Hierarchy of Truth'.
pub fn load_config(profile: &str) -> Result<AppConfig, Box<dyn std::error::Error>> {
    AppConfig::load_config(profile, None)
}

/// Semantic helper to match Go LoadConfigWithLogger().
pub fn load_config_with_logger(profile: &str, logger: Option<Arc<dyn Logger>>) -> Result<AppConfig, Box<dyn std::error::Error>> {
    AppConfig::load_config(profile, logger)
}

impl AppConfig {
    /// Loads and merges configuration data based on the provided profile.
    pub fn load_config(profile: &str, logger: Option<Arc<dyn Logger>>) -> Result<Self, Box<dyn std::error::Error>> {
        let cli_args = ToolboxArgs::parse_cli_args();
        
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
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        // ---------------------------------------------------------------------
        // BRIDGE INITIALIZATION (v1.9.8 Standard)
        // ---------------------------------------------------------------------
        if let Some(lib) = crate::config::ffi::get_lib() {
            let profile_c = CString::new(profile).unwrap();
            let handle = (lib.dist_conf_new)(profile_c.as_ptr());
            if handle != 0 {
                ac._handle = Some(handle);
                ac.logger.info(&format!("libdistconf session initialized (handle: {})", handle));
                ac.sync_from_bridge();
            }
        }

        // Phase 1: Load base config from file (Native Fallback)
        if ac._handle.is_none() {
            let mut filename = format!("{}.yaml", profile);
            if !std::path::Path::new(&filename).exists() {
                filename = format!("config/{}.yaml", profile);
            }
            ac.load_from_file(&filename);
        }

        // Phase 2: Layered logic matching Go implementation
        let is_dev = profile == "standalone" || profile == "test";
        if is_dev {
            ac.logger.info("Dev Mode detected. Re-applying Local File as Hard Override.");
            let mut filename = format!("{}.yaml", profile);
            if !std::path::Path::new(&filename).exists() {
                filename = format!("config/{}.yaml", profile);
            }
            ac.apply_file_override(&filename);
        } else {
            ac.logger.info("Production Mode detected. Config Server remains authoritative.");
        }

        ac.apply_cli_overrides();
        
        // If --key flag provided, set it as ENV override for the local Key (decryption engine)
        if let Some(key) = &ac.cli_args.key {
            unsafe {
                std::env::set_var("BASTIEN_local_KEY_PATH", key);
            }
        }

        ac.load_public_key();
        
        Ok(ac)
    }

    fn load_public_key(&mut self) {
        let mut path = std::env::var("BASTIEN_PUBLIC_KEY_PATH").unwrap_or_default();
        if path.is_empty() {
            path = "/etc/bastien/public.pem".to_string();
            if !std::path::Path::new(&path).exists() {
                if std::path::Path::new("./public.pem").exists() {
                    path = "./public.pem".to_string();
                } else {
                    return;
                }
            }
        }

        if let Ok(content) = fs::read_to_string(&path) {
            let _ = self.set_value("common.public_key", Value::String(content.trim().to_string()));
            self.logger.info(&format!("Public Key Loaded from {}", path));
        }
    }

    /// Explicitly decrypts a single ENC(...) ciphertext string.
    /// Uses the hardened distributed-config engine for cross-language consistency.
    pub fn decrypt_secret(&self, ciphertext: &str) -> Result<String, String> {
        if !ciphertext.starts_with("ENC(") || !ciphertext.ends_with(")") {
            return Ok(ciphertext.to_string());
        }

        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                let cipher_c = CString::new(ciphertext).map_err(|e| e.to_string())?;
                let ptr = unsafe { (lib.dist_conf_decrypt)(handle, cipher_c.as_ptr()) };
                if !ptr.is_null() && let Some(decrypted) = unsafe { crate::config::ffi::to_rust_string(ptr as *mut c_char) } {
                    return Ok(decrypted);
                }
                
                let err_ptr = unsafe { (lib.dist_conf_get_last_error)() };
                if !err_ptr.is_null() {
                    let c_str = unsafe { CStr::from_ptr(err_ptr) };
                    return Err(c_str.to_string_lossy().into_owned());
                }
                return Err("Unknown decryption error".to_string());
        }

        Err("Decryption not available (no bridge)".to_string())
    }

    fn load_from_file(&mut self, filename: &str) {
        if let Some(file_data) = self.read_and_expand_yaml(filename) {
            deep_merge(&mut self.data, &file_data);
        }
    }

    fn apply_file_override(&mut self, filename: &str) {
        if let Some(file_data) = self.read_and_expand_yaml(filename) {
            if let Some(caps) = file_data.get("capabilities") {
                if self.data.get("capabilities").is_none() {
                    let _ = self.set_value("capabilities", Value::Mapping(serde_yml::Mapping::new()));
                }
                if let Some(target_map) = self.data.get_mut("capabilities").and_then(|v| v.as_mapping_mut())
                    && let Some(source_map) = caps.as_mapping() {
                        for (k, v) in source_map {
                            target_map.insert(k.clone(), v.clone());
                        }
                }
            }
            if let Some(priv_data) = file_data.get("local") {
                if self.data.get("local").is_none() {
                    let _ = self.set_value("local", Value::Mapping(serde_yml::Mapping::new()));
                }
                if let Some(target_map) = self.data.get_mut("local").and_then(|v| v.as_mapping_mut())
                    && let Some(source_map) = priv_data.as_mapping() {
                        for (k, v) in source_map {
                            target_map.insert(k.clone(), v.clone());
                        }
                }
            }
        }
    }

    fn read_and_expand_yaml(&self, filename: &str) -> Option<Value> {
        let content = fs::read_to_string(filename).ok()?;
        
        // Expand Environment Variables: ${VAR} or ${VAR:default}
        let mut expanded = content.clone();
        let re = regex::Regex::new(r"\$\{([^}]+)\}").unwrap();
        
        for cap in re.captures_iter(&content) {
            let token = &cap[1];
            let parts: Vec<&str> = token.splitn(2, ':').collect();
            let var_name = parts[0];
            let default_val = parts.get(1).unwrap_or(&"");
            
            let final_val = std::env::var(var_name).unwrap_or_else(|_| default_val.to_string());
            expanded = expanded.replace(&cap[0], &final_val);
        }

        serde_yml::from_str::<Value>(&expanded).ok()
    }

    fn apply_cli_overrides(&mut self) {
        if let Some(name) = self.cli_args.name.clone() {
            let _ = self.set_value("common.name", Value::String(name));
        }

        let target = self.cli_args.name.clone()
            .or_else(|| self.get_value("common.name").and_then(|v| v.as_str()).map(|s| s.to_string()))
            .unwrap_or_else(|| "config_server".to_string());

        if self.cli_args.host.is_some() || self.cli_args.port.is_some() {
            if let Some(host) = &self.cli_args.host {
                let _ = self.set_value(&format!("capabilities.{}.ip", target), Value::String(host.clone()));
            }
            if let Some(p) = self.cli_args.port {
                let _ = self.set_value(&format!("capabilities.{}.port", target), Value::String(p.to_string()));
            }
        }

        if self.cli_args.grpc_host.is_some() || self.cli_args.grpc_port.is_some() {
            if let Some(gh) = &self.cli_args.grpc_host {
                let _ = self.set_value(&format!("capabilities.{}.grpc_ip", target), Value::String(gh.clone()));
            }
            if let Some(gp) = self.cli_args.grpc_port {
                let _ = self.set_value(&format!("capabilities.{}.grpc_port", target), Value::String(gp.to_string()));
            }
        }
    }

    pub fn set_logger(&mut self, logger: Arc<dyn Logger>) {
        self.logger = ensure_safe_logger(Some(logger));
        self.logger.info("Logger updated successfully");
    }

    pub fn common(&self) -> &Value {
        self.data.get(Value::String("common".to_string())).unwrap_or(&Value::Null)
    }

    pub fn get_local(&self, key: &str) -> Option<&Value> {
        self.get_value(&format!("local.{}", key))
    }

    /// Unmarshals the 'local' (local) configuration section into a target type.
    /// Parity with Go's UnmarshalLocal.
    pub fn unmarshal_local<T: serde::de::DeserializeOwned>(&self) -> Result<T, String> {
        let priv_val = self.data.get(Value::String("local".to_string()))
            .ok_or_else(|| "No local configuration found".to_string())?;
        serde_yml::from_value(priv_val.clone()).map_err(|e| e.to_string())
    }

    pub fn get_listen_addr(&self, capability: &str) -> Result<String, String> {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                let cap_c = CString::new(capability).map_err(|e| e.to_string())?;
                let ptr = (lib.dist_conf_get_address)(handle, cap_c.as_ptr());
                if let Some(addr) = unsafe { crate::config::ffi::to_rust_string(ptr) } {
                    return Ok(addr);
                }
        }
        self.get_addr(capability, "ip", "port")
    }

    pub fn get_grpc_listen_addr(&self, capability: &str) -> Result<String, String> {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                let cap_c = CString::new(capability).map_err(|e| e.to_string())?;
                let ptr = (lib.dist_conf_get_grpc_address)(handle, cap_c.as_ptr());
                if let Some(addr) = unsafe { crate::config::ffi::to_rust_string(ptr) } {
                    return Ok(addr);
                }
        }
        self.get_addr(capability, "grpc_ip", "grpc_port")
    }

    fn get_addr(&self, capability: &str, host_key: &str, port_key: &str) -> Result<String, String> {
        let cap_path = format!("capabilities.{}", capability);
        let cap = self.get_value(&cap_path).ok_or_else(|| format!("capability {} not found", capability))?;
        let host = cap.get(host_key).and_then(|v| v.as_str()).ok_or_else(|| format!("host key {} missing in capability {}", host_key, capability))?;
        let port = cap.get(port_key).and_then(|v| v.as_str()).ok_or_else(|| format!("port key {} missing in capability {}", port_key, capability))?;
        Ok(format!("{}:{}", host, port))
    }

    pub fn deep_merge(dst: &mut Value, src: &Value) {
        deep_merge(dst, src);
    }

    fn set_value(&mut self, path: &str, value: Value) -> Result<(), Box<dyn std::error::Error>> {
        let mut current = &mut self.data;
        let parts: Vec<&str> = path.split('.').collect();
        for part in parts.iter().take(parts.len() - 1) {
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

    fn sync_from_bridge(&mut self) {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                let ptr = (lib.dist_conf_get_full_config)(handle);
                if let Some(json_str) = unsafe { crate::config::ffi::to_rust_string(ptr) }
                    && let Ok(val) = serde_json::from_str::<serde_json::Value>(&json_str)
                    && let Ok(yml_val) = serde_yml::from_str::<Value>(&val.to_string()) {
                        self.data = yml_val;
                }
        }
    }

    pub fn get_config(&self, section: &str, key: &str) -> Option<String> {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                let section_c = CString::new(section).ok()?;
                let key_c = CString::new(key).ok()?;
                let ptr = (lib.dist_conf_get)(handle, section_c.as_ptr(), key_c.as_ptr());
                return unsafe { crate::config::ffi::to_rust_string(ptr) };
        }
        self.get_value(&format!("{}.{}", section, key)).and_then(|v| v.as_str()).map(|s| s.to_string())
    }

    pub fn on_live_conf_update<F>(&mut self, cb: F) 
    where F: Fn(serde_json::Value) + Send + Sync + 'static {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                
                *get_live_cb().lock().unwrap() = Some(Box::new(cb));
                
                extern "C" fn internal_cb(_handle: usize, json_ptr: *const std::os::raw::c_char) {
                    if let Some(json_str) = unsafe { crate::config::ffi::to_rust_string(json_ptr as *mut _) }
                        && let Ok(val) = serde_json::from_str::<serde_json::Value>(&json_str)
                        && let Ok(guard) = get_live_cb().lock()
                        && let Some(cb) = guard.as_ref() {
                            cb(val);
                    }
                }

                (lib.dist_conf_on_live_conf_update)(handle, internal_cb);
        }
    }

    pub fn on_registry_update<F>(&mut self, cb: F) 
    where F: Fn(serde_json::Value) + Send + Sync + 'static {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                
                *get_reg_cb().lock().unwrap() = Some(Box::new(cb));
                
                extern "C" fn internal_reg_cb(_handle: usize, json_ptr: *const std::os::raw::c_char) {
                    if let Some(json_str) = unsafe { crate::config::ffi::to_rust_string(json_ptr as *mut _) }
                        && let Ok(val) = serde_json::from_str::<serde_json::Value>(&json_str)
                        && let Ok(guard) = get_reg_cb().lock()
                        && let Some(cb) = guard.as_ref() {
                            cb(val);
                    }
                }

                (lib.dist_conf_on_registry_update)(handle, internal_reg_cb);
        }
    }

    pub fn share_config(&self, payload: &serde_json::Value) -> bool {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                let json_data = CString::new(payload.to_string()).unwrap();
                return (lib.dist_conf_share_config)(handle, json_data.as_ptr());
        }
        false
    }
}

impl Drop for AppConfig {
    fn drop(&mut self) {
        if let Some(handle) = self._handle
            && let Some(lib) = crate::config::ffi::get_lib() {
                (lib.dist_conf_close)(handle);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    static ENV_MUTEX: Mutex<()> = Mutex::new(());

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
    fn test_decrypt_plaintext_passthrough() {
        // Without a bridge, non-ENC strings should pass through
        let ac = AppConfig {
            profile: "test".to_string(),
            data: Value::Mapping(serde_yml::Mapping::new()),
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        assert_eq!(ac.decrypt_secret("normal_pass").unwrap(), "normal_pass");
        assert_eq!(ac.decrypt_secret("").unwrap(), "");
        // Missing closing paren — not a valid ENC block, should pass through
        assert_eq!(ac.decrypt_secret("ENC(no-close").unwrap(), "ENC(no-close");
        // Not starting with ENC( — should pass through
        assert_eq!(ac.decrypt_secret("not-ENC(data)").unwrap(), "not-ENC(data)");
    }

    #[test]
    fn test_decrypt_enc_block_errors_without_bridge() {
        let ac = AppConfig {
            profile: "test".to_string(),
            data: Value::Mapping(serde_yml::Mapping::new()),
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        // Valid ENC() block but no bridge → must return Err
        let result = ac.decrypt_secret("ENC(dummy)");
        assert!(result.is_err());
    }

    #[test]
    fn test_get_local() {
        let yaml_str = "local:\n  local_setting: value_xyz\n  nested:\n    val: 123\n    key: nested_value";
        let data = serde_yml::from_str::<Value>(yaml_str).unwrap();

        let ac = AppConfig {
            profile: "test".to_string(),
            data,
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        assert_eq!(ac.get_local("local_setting").unwrap().as_str().unwrap(), "value_xyz");
        assert_eq!(ac.get_local("nested.val").unwrap().as_u64().unwrap(), 123);
        assert_eq!(ac.get_local("nested.key").unwrap().as_str().unwrap(), "nested_value");
        assert!(ac.get_local("missing").is_none());
    }

    #[test]
    fn test_unmarshal_local() -> Result<(), String> {
        let _lock = ENV_MUTEX.lock().unwrap();
        let yaml_str = "local:\n  local_setting: value_xyz\n  item_count: 5";
        std::fs::write("unmarshal.yaml", yaml_str).map_err(|e| e.to_string())?;
        
        #[derive(serde::Deserialize)]
        struct MyConfig {
            local_setting: String,
            item_count: u64,
        }

        let ac = AppConfig::load_config("unmarshal", None).map_err(|e| e.to_string())?;
        let cfg: MyConfig = ac.unmarshal_local()?;
        
        assert_eq!(cfg.local_setting, "value_xyz");
        assert_eq!(cfg.item_count, 5);
        
        std::fs::remove_file("unmarshal.yaml").ok();
        Ok(())
    }

    #[test]
    fn test_get_local_empty() {
        let data = serde_yml::from_str::<Value>("common:\n  name: test").unwrap();

        let ac = AppConfig {
            profile: "test".to_string(),
            data,
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        assert!(ac.get_local("anything").is_none());
    }

    #[test]
    fn test_address_resolution() {
        let yaml_str = "capabilities:\n  svc:\n    ip: 1.2.3.4\n    port: '8080'\n    grpc_ip: 1.2.3.4\n    grpc_port: '8081'";
        let data = serde_yml::from_str::<Value>(yaml_str).unwrap();

        let ac = AppConfig {
            profile: "test".to_string(),
            data,
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        assert_eq!(ac.get_listen_addr("svc").unwrap(), "1.2.3.4:8080");
        assert_eq!(ac.get_grpc_listen_addr("svc").unwrap(), "1.2.3.4:8081");
    }

    #[test]
    fn test_grpc_missing_returns_error() {
        let yaml_str = "capabilities:\n  svc:\n    ip: 1.2.3.4\n    port: '8080'";
        let data = serde_yml::from_str::<Value>(yaml_str).unwrap();

        let ac = AppConfig {
            profile: "test".to_string(),
            data,
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        // No grpc_ip/grpc_port → must return error (no port+1 fallback)
        assert!(ac.get_grpc_listen_addr("svc").is_err());
    }

    #[test]
    fn test_set_logger() {
        let mut ac = AppConfig {
            profile: "test".to_string(),
            data: Value::Mapping(serde_yml::Mapping::new()),
            cli_args: ToolboxArgs::default(),
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        let new_logger = ensure_safe_logger(None);
        ac.set_logger(new_logger);
        // Should not panic — logger is wrapped safely
    }

    #[test]
    fn test_cli_override_targets_single_capability() {
        let yaml_str = "common:\n  name: my-svc\ncapabilities:\n  my-svc:\n    ip: '0.0.0.0'\n    port: '9000'\n  other-svc:\n    ip: '0.0.0.0'\n    port: '9001'";
        let data = serde_yml::from_str::<Value>(yaml_str).unwrap();

        let mut ac = AppConfig {
            profile: "test".to_string(),
            data,
            cli_args: ToolboxArgs {
                name: Some("my-svc".to_string()),
                host: Some("10.0.0.1".to_string()),
                port: Some(5555),
                ..Default::default()
            },
            logger: ensure_safe_logger(None),
            _handle: None,
            _live_cb: None,
            _reg_cb: None,
        };

        ac.apply_cli_overrides();

        // Target capability (my-svc) should be overridden
        assert_eq!(ac.get_listen_addr("my-svc").unwrap(), "10.0.0.1:5555");
        // Other capability should NOT be affected
        assert_eq!(ac.get_listen_addr("other-svc").unwrap(), "0.0.0.0:9001");
    }

    #[test]
    fn test_load_config_from_file() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = std::env::temp_dir().join("rust_toolbox_test");
        let _ = std::fs::create_dir_all(&dir);
        let yaml_str = "common:\n  name: file-test\ncapabilities:\n  svc:\n    ip: 5.6.7.8\n    port: '3000'\n    grpc_ip: 5.6.7.8\n    grpc_port: '3001'";
        let config_path = dir.join("file-test.yaml");
        std::fs::write(&config_path, yaml_str).unwrap();

        let old_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(&dir).unwrap();

        let result = load_config("file-test");
        std::env::set_current_dir(&old_dir).unwrap();
        let _ = std::fs::remove_file(&config_path);

        // If bridge is unavailable, falls back to file loading
        let ac = result.unwrap();
        assert_eq!(ac.profile, "file-test");
        assert_eq!(ac.get_listen_addr("svc").unwrap(), "5.6.7.8:3000");
        assert_eq!(ac.get_grpc_listen_addr("svc").unwrap(), "5.6.7.8:3001");
    }

    #[test]
    fn test_missing_file_returns_error() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = std::env::temp_dir().join("rust_toolbox_missing");
        let _ = std::fs::create_dir_all(&dir);
        let old_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(&dir).unwrap();

        let result = load_config("nonexistent-profile");
        std::env::set_current_dir(&old_dir).unwrap();

        // Without bridge and without file, data should be empty and addresses should fail
        let ac = result.unwrap();
        assert!(ac.get_listen_addr("anything").is_err());
    }

    #[test]
    fn test_env_expansion() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let yaml_str = "local:\n  host: \"${TEST_HOST:localhost}\"\n  port: \"${TEST_PORT:8080}\"";
        let dir = std::env::temp_dir().join("rust_toolbox_env");
        let _ = std::fs::create_dir_all(&dir);
        let config_path = dir.join("standalone.yaml");
        std::fs::write(&config_path, yaml_str).unwrap();

        unsafe {
            std::env::set_var("TEST_HOST", "127.0.0.5");
            std::env::remove_var("TEST_PORT");
        }

        let old_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(&dir).unwrap();

        let ac = load_config("standalone").unwrap();
        std::env::set_current_dir(&old_dir).unwrap();
        let _ = std::fs::remove_file(&config_path);

        assert_eq!(ac.get_local("host").unwrap().as_str().unwrap(), "127.0.0.5");
        assert_eq!(ac.get_local("port").unwrap().as_str().unwrap(), "8080");
    }
}
