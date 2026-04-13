use std::sync::Arc;
use microservice_toolbox::utils::logger::{UniLogger, Logger};
use microservice_toolbox::conn_manager::manager::new_network_manager_with_logger;
use microservice_toolbox::config::loader::load_config_with_logger;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!(">>> Initializing UniLogger (compiled Go engine)...");
    
    // 1. Initialize UniLogger (this loads the DLL via unilog crate)
    let config_profile = "standalone";
    let u_log = unilog_rs::UniLog::new("standalone", "test-rust", "standard", unilog_rs::LogLevel::Info, true)?;
    let logger: Arc<dyn Logger> = Arc::new(UniLogger::new(u_log));

    logger.info("Rust Toolbox modernized with compiled universal-logger!");

    // 2. Test NetworkManager with UniLogger
    println!(">>> Testing NetworkManager with UniLogger...");
    let nm = new_network_manager_with_logger(
        2,      // max retries
        200,    // base delay
        1000,   // max delay
        1000,   // timeout
        2.0,    // backoff
        0.1,    // jitter
        Some(logger.clone()),
    );

    // This should fail to connect but LOG via our UniLogger
    println!(">>> Expected failure logs should appear below (from Go core):");
    let _ = nm.connect_with_retry("localhost".to_string(), "1234".to_string()).await;

    // 3. Test AppConfig with UniLogger
    println!(">>> Testing AppConfig with UniLogger...");
    let config = load_config_with_logger(config_profile, Some(logger.clone()))?;
    println!(">>> Config loaded for profile: {}", config.profile);

    println!(">>> SUCCESS: Rust Toolbox modernized with compiled universal-logger!");
    Ok(())
}
