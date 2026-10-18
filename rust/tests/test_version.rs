use std::sync::Mutex;
use microservice_toolbox::version::get_version;
use microservice_toolbox::config::loader::AppConfig;

static ENV_MUTEX: Mutex<()> = Mutex::new(());

#[test]
fn test_default_version_resolution() {
    let _guard = ENV_MUTEX.lock().unwrap();
    let ver = get_version();
    assert_eq!(ver, "0.0.1");
}

#[test]
fn test_env_override_version() {
    let _guard = ENV_MUTEX.lock().unwrap();
    unsafe {
        std::env::set_var("APP_VERSION", "4.1.0");
    }
    let ver = get_version();
    assert_eq!(ver, "4.1.0");
    unsafe {
        std::env::remove_var("APP_VERSION");
    }
}

#[test]
fn test_app_config_get_version() {
    let _guard = ENV_MUTEX.lock().unwrap();
    let ac = AppConfig::default();
    assert_eq!(ac.get_version(), "0.0.1");
}
