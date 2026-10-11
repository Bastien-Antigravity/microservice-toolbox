// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit and integration tests for Rust NotificationClient facade in microservice-toolbox.
//
// DATA FLOW:
// Test -> NotificationClient -> Mock gRPC Server -> Assertion Verification
// -----------------------------------------------------------------------------

use std::sync::Arc;
use std::time::Duration;

use tokio::sync::Mutex;
use tonic::{Request, Response, Status};

use microservice_toolbox::config::loader::AppConfig;
use microservice_toolbox::notification::proto::{
    notif_service_server::{NotifService, NotifServiceServer},
    NotifRequest, NotifResponse,
};
use microservice_toolbox::notification::NotificationClient;

// -----------------------------------------------------------------------------
// Mock Server Implementation
// -----------------------------------------------------------------------------

struct MockNotifServer {
    success: bool,
    received_req: Arc<Mutex<Option<NotifRequest>>>,
}

#[tonic::async_trait]
impl NotifService for MockNotifServer {
    async fn send_notification(
        &self,
        request: Request<NotifRequest>,
    ) -> Result<Response<NotifResponse>, Status> {
        let req = request.into_inner();
        let mut guard = self.received_req.lock().await;
        *guard = Some(req);
        Ok(Response::new(NotifResponse {
            success: self.success,
        }))
    }
}

async fn start_mock_server(success: bool) -> (Arc<Mutex<Option<NotifRequest>>>, String, tokio::sync::oneshot::Sender<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    drop(listener);

    let received_req = Arc::new(Mutex::new(None));
    let service = MockNotifServer {
        success,
        received_req: received_req.clone(),
    };

    let server_addr = format!("127.0.0.1:{}", port).parse().unwrap();
    let (shutdown_tx, shutdown_rx) = tokio::sync::oneshot::channel::<()>();

    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(NotifServiceServer::new(service))
            .serve_with_shutdown(server_addr, async {
                let _ = shutdown_rx.await;
            })
            .await
            .unwrap();
    });

    tokio::time::sleep(Duration::from_millis(50)).await;
    (received_req, format!("127.0.0.1:{}", port), shutdown_tx)
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

#[tokio::test]
async fn test_notification_send_success() {
    let (received, addr, shutdown) = start_mock_server(true).await;

    let client = NotificationClient::new(&addr, None);
    let res = client.send("Hello from Rust L2 service", &["telegram", "discord"]).await;
    assert!(res.is_ok(), "expected Ok, got: {:?}", res);

    let req = received.lock().await.clone().expect("expected received request");
    assert_eq!(req.message, "Hello from Rust L2 service");
    assert_eq!(req.tags, vec!["telegram".to_string(), "discord".to_string()]);
    assert_eq!(req.level, "");

    let _ = shutdown.send(());
}

#[tokio::test]
async fn test_notification_send_alert() {
    let (received, addr, shutdown) = start_mock_server(true).await;

    let client = NotificationClient::new(&addr, None);
    let res = client.send_alert("TRADE", "Filled order #1092: Sold 2.5 BTC", &["trade_channel"]).await;
    assert!(res.is_ok());

    let req = received.lock().await.clone().expect("expected received request");
    assert_eq!(req.message, "Filled order #1092: Sold 2.5 BTC");
    assert_eq!(req.level, "TRADE");
    assert_eq!(req.tags, vec!["trade_channel".to_string()]);

    let _ = shutdown.send(());
}

#[tokio::test]
async fn test_notification_send_with_attachment() {
    let (received, addr, shutdown) = start_mock_server(true).await;

    let client = NotificationClient::new(&addr, None);
    let res = client.send_with_attachment("REPORT", "Daily PnL", "/tmp/report.pdf", &["finance"]).await;
    assert!(res.is_ok());

    let req = received.lock().await.clone().expect("expected received request");
    assert_eq!(req.message, "Daily PnL");
    assert_eq!(req.level, "REPORT");
    assert_eq!(req.attachment, "/tmp/report.pdf");
    assert_eq!(req.tags, vec!["finance".to_string()]);

    let _ = shutdown.send(());
}

#[tokio::test]
async fn test_notification_server_rejection() {
    let (_received, addr, shutdown) = start_mock_server(false).await;

    let client = NotificationClient::new(&addr, None);
    let res = client.send("Test message", &[]).await;
    assert!(res.is_err());
    assert!(res.err().unwrap().contains("notification server rejected message"));

    let _ = shutdown.send(());
}

#[tokio::test]
async fn test_notification_closed_client() {
    let client = NotificationClient::new("127.0.0.1:9999", None);
    client.close();
    let res = client.send("Should fail", &[]).await;
    assert!(res.is_err());
    assert!(res.err().unwrap().contains("closed"));
}

#[tokio::test]
async fn test_notification_from_config_resolution() {
    let (_received, addr, shutdown) = start_mock_server(true).await;

    let parts: Vec<&str> = addr.split(':').collect();
    let host = parts[0];
    let port: u16 = parts[1].parse().unwrap();

    let yaml_str = format!("capabilities:\n  notif_server:\n    grpc_ip: '{}'\n    grpc_port: '{}'", host, port);
    let data: serde_yml::Value = serde_yml::from_str(&yaml_str).unwrap();
    let ac = AppConfig::from_value(data);

    let client = NotificationClient::from_config(&ac, None);
    assert!(client.is_ok());
    let client = client.unwrap();

    let res = client.send("Config resolution test", &["telegram"]).await;
    assert!(res.is_ok());

    let _ = shutdown.send(());
}

#[tokio::test]
async fn test_notification_missing_capability_fails_fast() {
    let data: serde_yml::Value = serde_yml::from_str("capabilities: {}").unwrap();
    let ac = AppConfig::from_value(data);

    let client = NotificationClient::from_config(&ac, None);
    assert!(client.is_err());
    let err_msg = client.err().unwrap();
    assert!(err_msg.contains("failed to resolve notif_server gRPC address"));
}
