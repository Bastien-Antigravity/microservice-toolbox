// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Dynamic foreign function interface (FFI) bindings to the CGO libnotif engine.
//
// DATA FLOW:
// Host Language -> FFI Bridge -> CGO libnotif Shared Library
//
// KEY PARAMETERS:
// - LIBNOTIF_PATH: Environment path to the libnotif shared library.
// -----------------------------------------------------------------------------

use std::os::raw::{c_char, c_double, c_int};
use std::sync::OnceLock;
use libloading::{Library, Symbol};

pub struct NotifLib {
    _lib: Library,
    pub notif_send: Symbol<'static, extern "C" fn(
        target_addr: *const c_char,
        level: *const c_char,
        message: *const c_char,
        attachment: *const c_char,
        tags_csv: *const c_char,
    ) -> c_int>,
    pub notif_send_with_timeout: Symbol<'static, extern "C" fn(
        target_addr: *const c_char,
        level: *const c_char,
        message: *const c_char,
        attachment: *const c_char,
        tags_csv: *const c_char,
        timeout_sec: c_double,
    ) -> c_int>,
    pub notif_get_last_error: Symbol<'static, unsafe extern "C" fn() -> *const c_char>,
    pub notif_free_string: Symbol<'static, extern "C" fn(ptr: *mut c_char)>,
    pub notif_close: Symbol<'static, extern "C" fn()>,
}

static LIB: OnceLock<Option<NotifLib>> = OnceLock::new();

pub fn get_lib() -> Option<&'static NotifLib> {
    LIB.get_or_init(|| {
        let lib_path = std::env::var("LIBNOTIF_PATH")
            .unwrap_or_else(|_| {
                let paths = [
                    "../../notif-server/notif/libnotif/libnotif.dylib",
                    "../../notif-server/notif/libnotif/libnotif.so",
                    "../notif-server/notif/libnotif/libnotif.dylib",
                    "../notif-server/notif/libnotif/libnotif.so",
                    "notif-server/notif/libnotif/libnotif.dylib",
                    "notif-server/notif/libnotif/libnotif.so",
                    "/usr/local/lib/libnotif.dylib",
                    "/usr/local/lib/libnotif.so",
                    "./libnotif.dylib",
                    "./libnotif.so",
                ];
                for p in paths {
                    if std::path::Path::new(p).exists() {
                        return p.to_string();
                    }
                }
                "../../notif-server/notif/libnotif/libnotif.dylib".to_string()
            });

        unsafe {
            let lib = Library::new(lib_path).ok()?;
            Some(NotifLib {
                notif_send: std::mem::transmute(lib.get::<extern "C" fn(*const c_char, *const c_char, *const c_char, *const c_char, *const c_char) -> c_int>(b"Notif_Send").ok()?),
                notif_send_with_timeout: std::mem::transmute(lib.get::<extern "C" fn(*const c_char, *const c_char, *const c_char, *const c_char, *const c_char, c_double) -> c_int>(b"Notif_SendWithTimeout").ok()?),
                notif_get_last_error: std::mem::transmute(lib.get::<unsafe extern "C" fn() -> *const c_char>(b"Notif_GetLastError").ok()?),
                notif_free_string: std::mem::transmute(lib.get::<extern "C" fn(*mut c_char)>(b"Notif_FreeString").ok()?),
                notif_close: std::mem::transmute(lib.get::<extern "C" fn()>(b"Notif_Close").ok()?),
                _lib: lib,
            })
        }
    }).as_ref()
}
