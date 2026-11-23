// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Client facade connecting Rust services to the central tele-remote Telegram bot via gRPC.
//
// DATA FLOW:
// Service State / Actions -> TeleClient -> gRPC Stream -> TeleRemote Server -> Telegram Bot
//
// KEY PARAMETERS:
// - component_name: Unique service identifier displayed in Telegram menus.
// - target_ip / target_port: Network address of the central tele-remote service.
// -----------------------------------------------------------------------------

use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock as StdRwLock};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::sync::{mpsc, RwLock};
use tokio_stream::wrappers::ReceiverStream;
use tonic::metadata::MetadataValue;

use crate::config::loader::AppConfig;
use crate::config::LocalTLSConfig;
use crate::network::tls::{build_client_endpoint, normalize_tls_mode};
use crate::utils::logger::{ensure_safe_logger, Logger};

use super::proto::{
    bot_command::CommandType,
    component_message::Payload,
    tele_remote_service_client::TeleRemoteServiceClient,
    ComponentMessage, Registration,
};

//-----------------------------------------------------------------------------------------------
// Callback and Action Definitions
//-----------------------------------------------------------------------------------------------

pub type CallbackResult = Result<(), Box<dyn std::error::Error + Send + Sync>>;
pub type ActionCallback = Arc<dyn Fn(String) -> Pin<Box<dyn Future<Output = CallbackResult> + Send>> + Send + Sync>;

/// Action defines a single interactive element in the Telegram UI.
#[derive(Clone)]
pub struct Action {
    pub label: String,
    pub order: i32,
    pub sub_menu: Vec<Action>,
    pub input_prompt: String,
    pub callback: Option<ActionCallback>,
}

impl Action {
    pub fn new(label: &str) -> Self {
        Self {
            label: label.to_string(),
            order: 0,
            sub_menu: Vec::new(),
            input_prompt: String::new(),
            callback: None,
        }
    }

    pub fn with_order(mut self, order: i32) -> Self {
        self.order = order;
        self
    }

    pub fn with_callback<F, Fut>(mut self, cb: F) -> Self
    where
        F: Fn(String) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = CallbackResult> + Send + 'static,
    {
        self.callback = Some(Arc::new(move |input| Box::pin(cb(input))));
        self
    }

    pub fn with_input_prompt(mut self, prompt: &str) -> Self {
        self.input_prompt = prompt.to_string();
        self
    }

    pub fn with_sub_menu(mut self, sub_menu: Vec<Action>) -> Self {
        self.sub_menu = sub_menu;
        self
    }
}

//-----------------------------------------------------------------------------------------------
// Internal JSON Models for Menu Parity
//-----------------------------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone)]
struct BtnDef {
    label: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    order: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    cmd_type: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    payload: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    input_prompt: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    menu: Option<Vec<RowDef>>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct RowDef {
    #[serde(skip_serializing_if = "Option::is_none")]
    order: Option<i32>,
    buttons: Vec<BtnDef>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct MenuEnvelope {
    priority: i32,
    rows: Vec<RowDef>,
}

#[derive(Debug, Clone)]
struct TeleClientPolicy {
    priority: i32,
    auth_token: String,
    local_tls: LocalTLSConfig,
    tls_enabled: bool,
    tls_mode: String,
}

impl Default for TeleClientPolicy {
    fn default() -> Self {
        Self {
            priority: 0,
            auth_token: String::new(),
            local_tls: LocalTLSConfig::default(),
            tls_enabled: false,
            tls_mode: "auto".to_string(),
        }
    }
}

//-----------------------------------------------------------------------------------------------
// TeleClient Implementation
//-----------------------------------------------------------------------------------------------

/// TeleClient maintains a resilient gRPC connection to tele-remote.
pub struct TeleClient {
    component_name: String,
    target_ip: String,
    target_port: u16,
    logger: Arc<dyn Logger>,

    actions: Arc<RwLock<Vec<Action>>>,
    handlers: Arc<RwLock<HashMap<String, ActionCallback>>>,
    policy: Arc<StdRwLock<TeleClientPolicy>>,

    tx_outbound: Arc<tokio::sync::Mutex<Option<mpsc::Sender<ComponentMessage>>>>,
    closed: Arc<AtomicBool>,
    task_handle: Arc<std::sync::Mutex<Option<tokio::task::JoinHandle<()>>>>,
}

impl TeleClient {
    /// Creates a new TeleClient instance.
    pub fn new(
        component_name: &str,
        target_ip: &str,
        target_port: u16,
        logger: Option<Arc<dyn Logger>>,
    ) -> Self {
        Self {
            component_name: component_name.to_string(),
            target_ip: target_ip.to_string(),
            target_port,
            logger: ensure_safe_logger(logger),
            actions: Arc::new(RwLock::new(Vec::new())),
            handlers: Arc::new(RwLock::new(HashMap::new())),
            policy: Arc::new(StdRwLock::new(TeleClientPolicy::default())),
            tx_outbound: Arc::new(tokio::sync::Mutex::new(None)),
            closed: Arc::new(AtomicBool::new(false)),
            task_handle: Arc::new(std::sync::Mutex::new(None)),
        }
    }

    //-----------------------------------------------------------------------------------------------

    /// Returns a reference to the actions collection.
    pub fn actions(&self) -> &Arc<RwLock<Vec<Action>>> {
        &self.actions
    }

    /// Returns a reference to the registered command handlers map.
    pub fn handlers(&self) -> &Arc<RwLock<HashMap<String, ActionCallback>>> {
        &self.handlers
    }

    //-----------------------------------------------------------------------------------------------

    /// Configures the OpenMFE menu priority for this component.
    pub fn set_priority(&self, priority: i32) {
        if let Ok(mut guard) = self.policy.write() {
            guard.priority = priority;
        }
    }

    /// Configures the shared secret sent in outgoing `x-tele-auth` gRPC metadata.
    pub fn set_auth_token(&self, token: impl Into<String>) {
        if let Ok(mut guard) = self.policy.write() {
            guard.auth_token = token.into().trim().to_string();
        }
    }

    /// Configures service-private X.509 TLS/mTLS file paths from the `local:` section.
    pub fn set_local_tls(&self, cfg: LocalTLSConfig) {
        if let Ok(mut guard) = self.policy.write() {
            guard.local_tls = LocalTLSConfig {
                cert_file: cfg.cert_file.trim().to_string(),
                key_file: cfg.key_file.trim().to_string(),
                ca_file: cfg.ca_file.trim().to_string(),
                verify_client: cfg.verify_client,
            };
        }
    }

    /// Configures local/remote-aware TLS enforcement.
    pub fn set_tls_policy(&self, enabled: bool, mode: impl Into<String>) {
        if let Ok(mut guard) = self.policy.write() {
            guard.tls_enabled = enabled;
            guard.tls_mode = normalize_tls_mode(&mode.into());
        }
    }

    /// Loads local X.509 credentials, fleet `tele_remote` TLS/auth policy, and registers
    /// a live-configuration callback to refresh policy dynamically at runtime.
    pub fn configure_from_app_config(&self, app_config: &AppConfig, service_key: &str) -> Result<(), String> {
        let cap = app_config.get_capability("tele_remote")?;
        let (tls_enabled, tls_mode, auth_token) = Self::parse_tele_remote_capability(&cap, |cipher| {
            app_config.decrypt_secret(cipher)
        })?;

        self.set_local_tls(app_config.get_local_tls_config(service_key));
        self.set_tls_policy(tls_enabled, tls_mode);
        self.set_auth_token(auth_token);

        if let Some(handle) = app_config.bridge_handle() {
            let policy_ref = self.policy.clone();
            let logger_ref = self.logger.clone();
            app_config.on_live_conf_update(move |_update| {
                match AppConfig::get_capability_by_handle(handle, "tele_remote") {
                    Ok(live_cap) => {
                        match Self::parse_tele_remote_capability(&live_cap, |cipher| {
                            AppConfig::decrypt_secret_by_handle(Some(handle), cipher)
                        }) {
                            Ok((enabled, mode, token)) => {
                                if let Ok(mut guard) = policy_ref.write() {
                                    guard.tls_enabled = enabled;
                                    guard.tls_mode = normalize_tls_mode(&mode);
                                    guard.auth_token = token.trim().to_string();
                                }
                            }
                            Err(e) => {
                                logger_ref.warning(&format!("TeleClient live config refresh failed: {}", e));
                            }
                        }
                    }
                    Err(e) => {
                        logger_ref.warning(&format!("TeleClient live config refresh failed: {}", e));
                    }
                }
            });
        }

        Ok(())
    }

    fn parse_tele_remote_capability<F>(
        cap: &serde_json::Value,
        decrypt_fn: F,
    ) -> Result<(bool, String, String), String>
    where
        F: Fn(&str) -> Result<String, String>,
    {
        let tls_enabled = Self::parse_capability_bool(cap.get("tls_enabled"))
            .map_err(|e| format!("invalid tele_remote.tls_enabled: {}", e))?;

        let tls_mode = match cap.get("tls_mode") {
            None | Some(serde_json::Value::Null) => String::new(),
            Some(serde_json::Value::String(s)) => s.clone(),
            Some(_) => return Err("invalid tele_remote.tls_mode: expected string".to_string()),
        };

        let raw_token = match cap.get("auth_token") {
            None | Some(serde_json::Value::Null) => String::new(),
            Some(serde_json::Value::String(s)) => s.trim().to_string(),
            Some(_) => return Err("invalid tele_remote.auth_token: expected string".to_string()),
        };

        let auth_token = if raw_token.is_empty() {
            String::new()
        } else {
            decrypt_fn(&raw_token)
                .map_err(|e| format!("failed to decrypt tele_remote.auth_token: {}", e))?
        };

        Ok((tls_enabled, tls_mode, auth_token))
    }

    fn parse_capability_bool(raw: Option<&serde_json::Value>) -> Result<bool, String> {
        match raw {
            None | Some(serde_json::Value::Null) => Ok(false),
            Some(serde_json::Value::Bool(b)) => Ok(*b),
            Some(serde_json::Value::String(s)) => {
                match s.trim().to_ascii_lowercase().as_str() {
                    "" | "false" => Ok(false),
                    "true" => Ok(true),
                    _ => Err(format!("expected boolean or \"true\"/\"false\", got {:?}", s)),
                }
            }
            Some(other) => Err(format!("expected boolean or string, got {}", other)),
        }
    }

    //-----------------------------------------------------------------------------------------------

    /// Registers a new action or submenu tree.
    pub async fn add_action(&self, action: Action) {
        let mut actions = self.actions.write().await;
        actions.push(action.clone());
        let mut handlers = self.handlers.write().await;
        Self::register_handlers_recursive(&action, &mut handlers);
    }

    /// Replaces all current actions and handlers.
    pub async fn update_actions(&self, new_actions: Vec<Action>) {
        let mut actions = self.actions.write().await;
        *actions = new_actions.clone();
        let mut handlers = self.handlers.write().await;
        handlers.clear();
        for action in &new_actions {
            Self::register_handlers_recursive(action, &mut handlers);
        }
    }

    fn register_handlers_recursive(
        action: &Action,
        handlers: &mut HashMap<String, ActionCallback>,
    ) {
        if let Some(ref cb) = action.callback {
            handlers.insert(action.label.clone(), cb.clone());
        }
        for sub in &action.sub_menu {
            Self::register_handlers_recursive(sub, handlers);
        }
    }

    //-----------------------------------------------------------------------------------------------

    /// Returns the structured JSON representation of the action tree.
    pub async fn generate_menu_json(&self) -> String {
        let actions = self.actions.read().await;
        let priority = self.policy.read().map(|p| p.priority).unwrap_or(0);
        Self::build_menu_json(&actions, priority)
    }

    fn build_menu_json(actions: &[Action], priority: i32) -> String {
        let mut rows = Vec::with_capacity(actions.len());
        for action in actions {
            let btn = Self::convert_action_to_btn(action);
            rows.push(RowDef {
                order: if action.order > 0 { Some(action.order) } else { None },
                buttons: vec![btn],
            });
        }
        if priority > 0 {
            serde_json::to_string(&MenuEnvelope { priority, rows }).unwrap_or_else(|_| "[]".to_string())
        } else {
            serde_json::to_string(&rows).unwrap_or_else(|_| "[]".to_string())
        }
    }

    fn convert_action_to_btn(action: &Action) -> BtnDef {
        let mut btn = BtnDef {
            label: action.label.clone(),
            order: if action.order > 0 { Some(action.order) } else { None },
            cmd_type: None,
            payload: None,
            input_prompt: if !action.input_prompt.is_empty() {
                Some(action.input_prompt.clone())
            } else {
                None
            },
            menu: None,
        };

        if !action.sub_menu.is_empty() || action.callback.is_none() {
            let mut sub_rows = Vec::with_capacity(action.sub_menu.len());
            for sub_a in &action.sub_menu {
                let sub_btn = Self::convert_action_to_btn(sub_a);
                sub_rows.push(RowDef {
                    order: if sub_a.order > 0 { Some(sub_a.order) } else { None },
                    buttons: vec![sub_btn],
                });
            }
            btn.menu = Some(sub_rows);
        } else {
            btn.cmd_type = Some(99);
            btn.payload = Some(action.label.clone());
        }

        btn
    }

    //-----------------------------------------------------------------------------------------------

    /// Manually triggers transmission of updated menu schema to tele-remote.
    pub async fn push_menu_update(&self) {
        let tx_opt = self.tx_outbound.lock().await;
        if let Some(ref tx) = *tx_opt {
            let menu = self.generate_menu_json().await;
            let msg = ComponentMessage {
                component_name: self.component_name.clone(),
                host: "127.0.0.1".to_string(),
                port: self.target_port as i32,
                payload: Some(Payload::Registration(Registration { menu_json: menu })),
            };
            let _ = tx.send(msg).await;
        }
    }

    /// Streams an arbitrary text telemetry message to the Telegram bot admin chat.
    pub async fn send_telemetry(&self, msg: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let tx_opt = self.tx_outbound.lock().await;
        if let Some(ref tx) = *tx_opt {
            let payload = ComponentMessage {
                component_name: self.component_name.clone(),
                host: "127.0.0.1".to_string(),
                port: self.target_port as i32,
                payload: Some(Payload::Telemetry(msg.to_string())),
            };
            tx.send(payload).await.map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
            Ok(())
        } else {
            Err("not connected to tele-remote".into())
        }
    }

    //-----------------------------------------------------------------------------------------------

    /// Spawns the background connection manager and command dispatcher.
    pub fn start(&self) {
        let component_name = self.component_name.clone();
        let target_ip = self.target_ip.clone();
        let target_port = self.target_port;
        let logger = self.logger.clone();
        let actions = self.actions.clone();
        let handlers = self.handlers.clone();
        let policy = self.policy.clone();
        let tx_outbound_mutex = self.tx_outbound.clone();
        let closed = self.closed.clone();

        let handle = tokio::spawn(async move {
            while !closed.load(Ordering::Relaxed) {
                let (local_tls, tls_enabled, tls_mode, auth_token, priority) = {
                    match policy.read() {
                        Ok(guard) => (
                            guard.local_tls.clone(),
                            guard.tls_enabled,
                            guard.tls_mode.clone(),
                            guard.auth_token.clone(),
                            guard.priority,
                        ),
                        Err(_) => (
                            LocalTLSConfig::default(),
                            false,
                            "auto".to_string(),
                            String::new(),
                            0,
                        ),
                    }
                };

                let endpoint = match build_client_endpoint(
                    &target_ip,
                    target_port as i32,
                    &local_tls,
                    tls_enabled,
                    &tls_mode,
                ) {
                    Ok(ep) => ep,
                    Err(e) => {
                        logger.warning(&format!(
                            "TeleClient failed to resolve TLS credentials for {}:{}: {}",
                            target_ip, target_port, e
                        ));
                        tokio::time::sleep(Duration::from_secs(5)).await;
                        continue;
                    }
                };

                logger.info(&format!("TeleClient connecting to {}:{}...", target_ip, target_port));

                let (tx, rx) = mpsc::channel::<ComponentMessage>(100);

                // Initial registration message
                let menu_json = {
                    let acts = actions.read().await;
                    let current_priority = policy.read().map(|p| p.priority).unwrap_or(priority);
                    Self::build_menu_json(&acts, current_priority)
                };

                let initial_reg = ComponentMessage {
                    component_name: component_name.clone(),
                    host: "127.0.0.1".to_string(),
                    port: target_port as i32,
                    payload: Some(Payload::Registration(Registration { menu_json })),
                };

                if let Err(e) = tx.send(initial_reg).await {
                    logger.warning(&format!("TeleClient failed to queue registration: {:?}", e));
                    tokio::time::sleep(Duration::from_secs(5)).await;
                    continue;
                }

                let channel = match endpoint.connect().await {
                    Ok(ch) => ch,
                    Err(e) => {
                        logger.warning(&format!("TeleClient connection failed: {:?}", e));
                        tokio::time::sleep(Duration::from_secs(5)).await;
                        continue;
                    }
                };

                let mut client = TeleRemoteServiceClient::new(channel);
                let request_stream = ReceiverStream::new(rx);
                let mut req = tonic::Request::new(request_stream);
                if !auth_token.is_empty() {
                    match MetadataValue::try_from(auth_token.as_str()) {
                        Ok(val) => {
                            req.metadata_mut().insert("x-tele-auth", val);
                        }
                        Err(e) => {
                            logger.warning(&format!("TeleClient invalid x-tele-auth metadata: {:?}", e));
                        }
                    }
                }

                match client.connect(req).await {
                    Ok(response) => {
                        {
                            let mut tx_lock = tx_outbound_mutex.lock().await;
                            *tx_lock = Some(tx.clone());
                        }
                        logger.info("TeleClient successfully registered with tele-remote");

                        let mut in_stream = response.into_inner();
                        while let Ok(Some(cmd)) = in_stream.message().await {
                            if closed.load(Ordering::Relaxed) {
                                break;
                            }

                            if cmd.command_type == CommandType::RefreshMenu as i32 {
                                logger.info("TeleClient received REFRESH_MENU request");
                                let current_menu = {
                                    let acts = actions.read().await;
                                    let current_priority = policy.read().map(|p| p.priority).unwrap_or(priority);
                                    Self::build_menu_json(&acts, current_priority)
                                };
                                let reg = ComponentMessage {
                                    component_name: component_name.clone(),
                                    host: "127.0.0.1".to_string(),
                                    port: target_port as i32,
                                    payload: Some(Payload::Registration(Registration { menu_json: current_menu })),
                                };
                                let _ = tx.send(reg).await;
                                continue;
                            }

                            let handler_opt = {
                                let h_map = handlers.read().await;
                                h_map.get(&cmd.custom_payload).cloned()
                            };

                            if let Some(handler) = handler_opt {
                                logger.info(&format!(
                                    "Executing automatic Tele-Remote command: {} (Input: {})",
                                    cmd.custom_payload, cmd.input
                                ));
                                let log = logger.clone();
                                tokio::spawn(async move {
                                    if let Err(e) = handler(cmd.input).await {
                                        log.error(&format!("Tele-Remote command handler failed: {:?}", e));
                                    }
                                });
                            } else {
                                logger.warning(&format!(
                                    "No handler registered for command payload: {}",
                                    cmd.custom_payload
                                ));
                            }
                        }
                    }
                    Err(e) => {
                        logger.warning(&format!("TeleClient stream creation failed: {:?}", e));
                    }
                }

                // Disconnect cleanup
                {
                    let mut tx_lock = tx_outbound_mutex.lock().await;
                    *tx_lock = None;
                }

                if !closed.load(Ordering::Relaxed) {
                    tokio::time::sleep(Duration::from_secs(5)).await;
                }
            }
        });

        if let Ok(mut th) = self.task_handle.lock() {
            *th = Some(handle);
        }
    }

    /// Gracefully closes the tele-remote client connection.
    pub async fn close(&self) {
        self.closed.store(true, Ordering::Relaxed);
        let mut tx_lock = self.tx_outbound.lock().await;
        *tx_lock = None;
        if let Ok(mut th) = self.task_handle.lock() {
            if let Some(handle) = th.take() {
                handle.abort();
            }
        }
    }
}
