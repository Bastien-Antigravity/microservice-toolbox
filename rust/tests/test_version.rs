use microservice_toolbox::config::loader::AppConfig;
use microservice_toolbox::version::{
    get_version, reset_version, set_version, try_resolve_version_in_dir,
};
use std::sync::Mutex;

static ENV_MUTEX: Mutex<()> = Mutex::new(());

#[test]
fn test_default_version_resolution() {
    let _guard = ENV_MUTEX.lock().unwrap();
    reset_version();
    let ver = get_version();
    assert_eq!(ver, "0.0.1");
}

#[test]
fn test_version_txt_directory_climb_ignores_env() {
    let _guard = ENV_MUTEX.lock().unwrap();
    reset_version();
    unsafe {
        std::env::set_var("APP_VERSION", "9.9.9");
        std::env::set_var("SERVICE_VERSION", "8.8.8");
    }
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!("mt_ver_found_{}", unique));
    let nested = root.join("src").join("bin");
    std::fs::create_dir_all(&nested).unwrap();
    std::fs::create_dir_all(root.join(".git")).unwrap();
    std::fs::write(root.join("VERSION.txt"), "4.1.0\n").unwrap();

    let resolved = try_resolve_version_in_dir(&nested).unwrap();
    unsafe {
        std::env::remove_var("APP_VERSION");
        std::env::remove_var("SERVICE_VERSION");
    }
    let _ = std::fs::remove_dir_all(&root);
    assert_eq!(resolved, "4.1.0");
}

#[test]
fn test_set_and_reset_version() {
    let _guard = ENV_MUTEX.lock().unwrap();
    reset_version();
    set_version("7.7.7");
    assert_eq!(get_version(), "7.7.7");
    reset_version();
}

#[test]
#[should_panic(expected = "FAIL-FAST")]
fn test_set_empty_version_fails_fast() {
    set_version("  ");
}

#[test]
fn test_fail_fast_when_version_file_missing() {
    let _guard = ENV_MUTEX.lock().unwrap();
    reset_version();
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("mt_ver_missing_{}", unique));
    std::fs::create_dir_all(dir.join(".git")).unwrap();

    let err = try_resolve_version_in_dir(&dir);
    let _ = std::fs::remove_dir_all(&dir);
    assert!(err.is_err());
}

#[test]
fn test_app_config_get_version() {
    let _guard = ENV_MUTEX.lock().unwrap();
    reset_version();
    let ac = AppConfig::default();
    assert_eq!(ac.get_version(), "0.0.1");
}
