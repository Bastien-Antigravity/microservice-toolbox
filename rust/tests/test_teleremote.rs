// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for Rust TeleClient action tree generation, menu JSON serialization,
// handler dispatching, and disconnected telemetry handling.
//
// DATA FLOW:
// Action Tree -> TeleClient -> generate_menu_json() / handlers -> JSON Assertion & Callback Execution
//
// KEY PARAMETERS:
// - None (Unit Test Suite).
// -----------------------------------------------------------------------------

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use microservice_toolbox::teleremote::{Action, TeleClient};

// -----------------------------------------------------------------------------
// Test Cases
// -----------------------------------------------------------------------------

#[tokio::test]
async fn test_action_and_menu_generation() {
    let client = TeleClient::new("TestApp", "127.0.0.1", 1863, None);

    let h1_called = Arc::new(AtomicBool::new(false));
    let h1_called_clone = h1_called.clone();
    let a1 = Action::new("Command 1").with_callback(move |_input| {
        let called = h1_called_clone.clone();
        Box::pin(async move {
            called.store(true, Ordering::SeqCst);
            Ok(())
        })
    });

    let h2_called = Arc::new(AtomicBool::new(false));
    let h2_called_clone = h2_called.clone();
    let sub_a = Action::new("Sub Command")
        .with_input_prompt("Enter text:")
        .with_callback(move |input| {
            let called = h2_called_clone.clone();
            Box::pin(async move {
                assert_eq!(input, "test input");
                called.store(true, Ordering::SeqCst);
                Ok(())
            })
        });

    let a2 = Action::new("Menu 1").with_sub_menu(vec![sub_a]);

    client.add_action(a1).await;
    client.add_action(a2).await;

    // Verify handler registration
    let handlers = client.handlers().read().await;
    assert!(handlers.contains_key("Command 1"));
    assert!(handlers.contains_key("Sub Command"));
    assert!(!handlers.contains_key("Menu 1")); // Submenu root has no callback

    // Test direct handler execution
    let h1 = handlers.get("Command 1").unwrap().clone();
    drop(handlers);
    let res1 = h1("".to_string()).await;
    assert!(res1.is_ok());
    assert!(h1_called.load(Ordering::SeqCst));

    let handlers = client.handlers().read().await;
    let h2 = handlers.get("Sub Command").unwrap().clone();
    drop(handlers);
    let res2 = h2("test input".to_string()).await;
    assert!(res2.is_ok());
    assert!(h2_called.load(Ordering::SeqCst));

    // Verify Menu JSON serialization
    let menu_json = client.generate_menu_json().await;
    let menu: serde_json::Value = serde_json::from_str(&menu_json).expect("valid json");

    let rows = menu.as_array().expect("array of rows");
    assert_eq!(rows.len(), 2);

    // Check leaf button
    let btn1 = &rows[0]["buttons"][0];
    assert_eq!(btn1["label"], "Command 1");
    assert_eq!(btn1["cmd_type"], 99);
    assert_eq!(btn1["payload"], "Command 1");
    assert!(btn1.get("input_prompt").is_none());
    assert!(btn1.get("menu").is_none());

    // Check submenu button
    let btn2 = &rows[1]["buttons"][0];
    assert_eq!(btn2["label"], "Menu 1");
    assert!(btn2.get("cmd_type").is_none());
    assert!(btn2.get("payload").is_none());
    assert!(btn2.get("input_prompt").is_none());
    assert!(btn2.get("menu").is_some());

    let sub_btn = &btn2["menu"][0]["buttons"][0];
    assert_eq!(sub_btn["label"], "Sub Command");
    assert_eq!(sub_btn["input_prompt"], "Enter text:");
    assert_eq!(sub_btn["cmd_type"], 99);
    assert_eq!(sub_btn["payload"], "Sub Command");
}

#[tokio::test]
async fn test_update_actions() {
    let client = TeleClient::new("TestApp", "127.0.0.1", 1863, None);

    let a1 = Action::new("Initial").with_callback(|_| Box::pin(async { Ok(()) }));
    client.add_action(a1).await;

    {
        let actions = client.actions().read().await;
        let handlers = client.handlers().read().await;
        assert_eq!(actions.len(), 1);
        assert!(handlers.contains_key("Initial"));
    }

    let a2 = Action::new("Replaced").with_callback(|_| Box::pin(async { Ok(()) }));
    client.update_actions(vec![a2]).await;

    {
        let actions = client.actions().read().await;
        let handlers = client.handlers().read().await;
        assert_eq!(actions.len(), 1);
        assert!(!handlers.contains_key("Initial"));
        assert!(handlers.contains_key("Replaced"));
    }
}

#[tokio::test]
async fn test_send_telemetry_disconnected() {
    let client = TeleClient::new("TestApp", "127.0.0.1", 1863, None);
    let res = client.send_telemetry("test message").await;
    assert!(res.is_err());
    let err_msg = res.err().unwrap().to_string();
    assert!(
        err_msg.contains("not connected to tele-remote"),
        "unexpected error message: {}",
        err_msg
    );
}

// -----------------------------------------------------------------------------
// Mock gRPC Server & E2E Integration Test
// -----------------------------------------------------------------------------

use microservice_toolbox::teleremote::proto::{
    self,
    bot_command::CommandType,
    tele_remote_service_server::{TeleRemoteService, TeleRemoteServiceServer},
    BotCommand, ComponentMessage,
};
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;

struct MockTeleRemoteService {
    registrations: Arc<tokio::sync::Mutex<Vec<ComponentMessage>>>,
    telemetries: Arc<tokio::sync::Mutex<Vec<String>>>,
    cmd_rx: Arc<tokio::sync::Mutex<Option<mpsc::Receiver<Result<BotCommand, tonic::Status>>>>>,
}

#[tonic::async_trait]
impl TeleRemoteService for MockTeleRemoteService {
    type ConnectStream = ReceiverStream<Result<BotCommand, tonic::Status>>;

    async fn connect(
        &self,
        request: tonic::Request<tonic::Streaming<ComponentMessage>>,
    ) -> Result<tonic::Response<Self::ConnectStream>, tonic::Status> {
        let mut in_stream = request.into_inner();
        let regs = self.registrations.clone();
        let tels = self.telemetries.clone();

        tokio::spawn(async move {
            while let Ok(Some(msg)) = in_stream.message().await {
                if let Some(ref payload) = msg.payload {
                    match payload {
                        proto::component_message::Payload::Registration(_) => {
                            let mut r = regs.lock().await;
                            r.push(msg.clone());
                        }
                        proto::component_message::Payload::Telemetry(t) => {
                            let mut tel = tels.lock().await;
                            tel.push(t.clone());
                        }
                        _ => {}
                    }
                }
            }
        });

        let mut rx_guard = self.cmd_rx.lock().await;
        let rx = rx_guard.take().expect("cmd_rx should only be taken once");
        Ok(tonic::Response::new(ReceiverStream::new(rx)))
    }
}

#[tokio::test]
async fn test_teleclient_e2e_streaming() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    drop(listener);

    let (cmd_tx, cmd_rx) = mpsc::channel(10);
    let registrations = Arc::new(tokio::sync::Mutex::new(Vec::new()));
    let telemetries = Arc::new(tokio::sync::Mutex::new(Vec::new()));

    let service = MockTeleRemoteService {
        registrations: registrations.clone(),
        telemetries: telemetries.clone(),
        cmd_rx: Arc::new(tokio::sync::Mutex::new(Some(cmd_rx))),
    };

    let server_addr = format!("127.0.0.1:{}", port).parse().unwrap();
    let (shutdown_tx, shutdown_rx) = tokio::sync::oneshot::channel::<()>();

    let server_handle = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(TeleRemoteServiceServer::new(service))
            .serve_with_shutdown(server_addr, async {
                let _ = shutdown_rx.await;
            })
            .await
            .unwrap();
    });

    // Wait a brief moment for server to bind
    tokio::time::sleep(Duration::from_millis(50)).await;

    let cmd_executed = Arc::new(AtomicBool::new(false));
    let cmd_executed_clone = cmd_executed.clone();
    let received_input = Arc::new(tokio::sync::Mutex::new(String::new()));
    let received_input_clone = received_input.clone();

    let client = TeleClient::new("E2EApp", "127.0.0.1", port, None);
    let action = Action::new("E2E_Command").with_callback(move |input| {
        let executed = cmd_executed_clone.clone();
        let input_store = received_input_clone.clone();
        Box::pin(async move {
            let mut store = input_store.lock().await;
            *store = input;
            executed.store(true, Ordering::SeqCst);
            Ok(())
        })
    });

    client.add_action(action).await;
    client.start();

    // 1. Verify Registration sent to server
    for _ in 0..30 {
        let regs = registrations.lock().await;
        if !regs.is_empty() {
            break;
        }
        drop(regs);
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    {
        let regs = registrations.lock().await;
        assert_eq!(regs.len(), 1, "Expected 1 registration message");
        assert_eq!(regs[0].component_name, "E2EApp");
        if let Some(proto::component_message::Payload::Registration(reg)) = &regs[0].payload {
            assert!(reg.menu_json.contains("E2E_Command"));
        } else {
            panic!("Expected registration payload");
        }
    }

    // 2. Verify Send Telemetry
    let res = client.send_telemetry("E2E Telemetry Message").await;
    assert!(res.is_ok(), "Telemetry should succeed when connected: {:?}", res);

    for _ in 0..30 {
        let tels = telemetries.lock().await;
        if !tels.is_empty() {
            break;
        }
        drop(tels);
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    {
        let tels = telemetries.lock().await;
        assert_eq!(tels.len(), 1);
        assert_eq!(tels[0], "E2E Telemetry Message");
    }

    // 3. Dispatch BotCommand from server to client
    let bot_cmd = BotCommand {
        command_type: CommandType::CustomCommand as i32,
        custom_payload: "E2E_Command".to_string(),
        input: "payload_from_telegram".to_string(),
    };
    cmd_tx.send(Ok(bot_cmd)).await.unwrap();

    for _ in 0..30 {
        if cmd_executed.load(Ordering::SeqCst) {
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    assert!(cmd_executed.load(Ordering::SeqCst), "Command callback should be triggered");
    {
        let input = received_input.lock().await;
        assert_eq!(*input, "payload_from_telegram");
    }

    // Clean up
    drop(cmd_tx);
    client.close().await;
    let _ = shutdown_tx.send(());
    let _ = server_handle.await;
}
