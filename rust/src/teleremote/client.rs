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
use std::sync::Arc;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::sync::{mpsc, RwLock};
use tokio_stream::wrappers::ReceiverStream;

use crate::utils::logger::{ensure_safe_logger, Logger};
use super::proto::{
    bot_command::CommandType,
    component_message::Payload,
    tele_remote_service_client::TeleRemoteServiceClient,
    ComponentMessage, Registration,
};

// -----------------------------------------------------------------------------
// Callback and Action Definitions
// -----------------------------------------------------------------------------

pub type CallbackResult = Result<(), Box<dyn std::error::Error + Send + Sync>>;
pub type ActionCallback = Arc<dyn Fn(String) -> Pin<Box<dyn Future<Output = CallbackResult> + Send>> + Send + Sync>;

/// Action defines a single interactive element in the Telegram UI.
#[derive(Clone)]
pub struct Action {
    pub label: String,
    pub sub_menu: Vec<Action>,
    pub input_prompt: String,
    pub callback: Option<ActionCallback>,
}

impl Action {
    pub fn new(label: &str) -> Self {
        Self {
            label: label.to_string(),
            sub_menu: Vec::new(),
            input_prompt: String::new(),
            callback: None,
        }
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

// -----------------------------------------------------------------------------
// Internal JSON Models for Menu Parity
// -----------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone)]
struct BtnDef {
    label: String,
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
    buttons: Vec<BtnDef>,
}

// -----------------------------------------------------------------------------
// TeleClient Implementation
// -----------------------------------------------------------------------------

/// TeleClient maintains a resilient gRPC connection to tele-remote.
pub struct TeleClient {
    component_name: String,
    target_ip: String,
    target_port: u16,
    logger: Arc<dyn Logger>,

    actions: Arc<RwLock<Vec<Action>>>,
    handlers: Arc<RwLock<HashMap<String, ActionCallback>>>,

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
            tx_outbound: Arc::new(tokio::sync::Mutex::new(None)),
            closed: Arc::new(AtomicBool::new(false)),
            task_handle: Arc::new(std::sync::Mutex::new(None)),
        }
    }

    // -----------------------------------------------------------------------------

    /// Returns a reference to the actions collection.
    pub fn actions(&self) -> &Arc<RwLock<Vec<Action>>> {
        &self.actions
    }

    /// Returns a reference to the registered command handlers map.
    pub fn handlers(&self) -> &Arc<RwLock<HashMap<String, ActionCallback>>> {
        &self.handlers
    }

    // -----------------------------------------------------------------------------

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

    // -----------------------------------------------------------------------------

    /// Returns the structured JSON representation of the action tree.
    pub async fn generate_menu_json(&self) -> String {
        let actions = self.actions.read().await;
        let mut rows = Vec::new();
        for action in actions.iter() {
            let btn = Self::convert_action_to_btn(action);
            rows.push(RowDef { buttons: vec![btn] });
        }
        serde_json::to_string(&rows).unwrap_or_else(|_| "[]".to_string())
    }

    fn convert_action_to_btn(action: &Action) -> BtnDef {
        let mut btn = BtnDef {
            label: action.label.clone(),
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
            let mut sub_rows = Vec::new();
            for sub_a in &action.sub_menu {
                let sub_btn = Self::convert_action_to_btn(sub_a);
                sub_rows.push(RowDef { buttons: vec![sub_btn] });
            }
            btn.menu = Some(sub_rows);
        } else {
            btn.cmd_type = Some(99);
            btn.payload = Some(action.label.clone());
        }

        btn
    }

    // -----------------------------------------------------------------------------

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

    // -----------------------------------------------------------------------------

    /// Spawns the background connection manager and command dispatcher.
    pub fn start(&self) {
        let component_name = self.component_name.clone();
        let target_ip = self.target_ip.clone();
        let target_port = self.target_port;
        let logger = self.logger.clone();
        let actions = self.actions.clone();
        let handlers = self.handlers.clone();
        let tx_outbound_mutex = self.tx_outbound.clone();
        let closed = self.closed.clone();

        let handle = tokio::spawn(async move {
            let addr = format!("http://{}:{}", target_ip, target_port);

            while !closed.load(Ordering::Relaxed) {
                logger.info(&format!("TeleClient connecting to {}...", addr));

                let (tx, rx) = mpsc::channel::<ComponentMessage>(100);

                // Initial registration message
                let menu_json = {
                    let acts = actions.read().await;
                    let mut rows = Vec::new();
                    for a in acts.iter() {
                        let btn = Self::convert_action_to_btn(a);
                        rows.push(RowDef { buttons: vec![btn] });
                    }
                    serde_json::to_string(&rows).unwrap_or_else(|_| "[]".to_string())
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

                // Attempt gRPC connection
                let endpoint = match tonic::transport::Channel::from_shared(addr.clone()) {
                    Ok(ep) => ep,
                    Err(e) => {
                        logger.warning(&format!("TeleClient invalid endpoint {}: {:?}", addr, e));
                        tokio::time::sleep(Duration::from_secs(5)).await;
                        continue;
                    }
                };

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
                match client.connect(request_stream).await {
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
                                            let mut rows = Vec::new();
                                            for a in acts.iter() {
                                                let btn = Self::convert_action_to_btn(a);
                                                rows.push(RowDef { buttons: vec![btn] });
                                            }
                                            serde_json::to_string(&rows).unwrap_or_else(|_| "[]".to_string())
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
