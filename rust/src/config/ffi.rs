use std::ffi::CStr;
use std::os::raw::{c_char, c_int};
use std::sync::OnceLock;
use libloading::{Library, Symbol};

pub type ConfigUpdateCb = extern "C" fn(handle: usize, json_data: *const c_char);

pub struct DistConfLib {
    _lib: Library,
    pub dist_conf_new: Symbol<'static, extern "C" fn(profile: *const c_char) -> usize>,
    pub dist_conf_close: Symbol<'static, extern "C" fn(handle: usize)>,
    pub dist_conf_get: Symbol<'static, extern "C" fn(handle: usize, section: *const c_char, key: *const c_char) -> *mut c_char>,
    pub dist_conf_set: Symbol<'static, extern "C" fn(handle: usize, section: *const c_char, key: *const c_char, value: *const c_char) -> bool>,
    pub dist_conf_sync: Symbol<'static, extern "C" fn(handle: usize) -> c_int>,
    pub dist_conf_on_live_conf_update: Symbol<'static, extern "C" fn(handle: usize, cb: ConfigUpdateCb)>,
    pub dist_conf_on_registry_update: Symbol<'static, extern "C" fn(handle: usize, cb: ConfigUpdateCb)>,
    pub dist_conf_get_address: Symbol<'static, extern "C" fn(handle: usize, capability: *const c_char) -> *mut c_char>,
    pub dist_conf_get_grpc_address: Symbol<'static, extern "C" fn(handle: usize, capability: *const c_char) -> *mut c_char>,
    pub dist_conf_get_capability: Symbol<'static, extern "C" fn(handle: usize, capability: *const c_char) -> *mut c_char>,
    pub dist_conf_get_full_config: Symbol<'static, extern "C" fn(handle: usize) -> *mut c_char>,
    pub dist_conf_get_last_error: Symbol<'static, unsafe extern "C" fn() -> *const c_char>,
    pub dist_conf_decrypt: Symbol<'static, unsafe extern "C" fn(handle: usize, ciphertext: *const c_char) -> *const c_char>,
    pub dist_conf_share_config: Symbol<'static, extern "C" fn(handle: usize, payload_json: *const c_char) -> bool>,
    pub dist_conf_free_string: Symbol<'static, extern "C" fn(ptr: *mut c_char)>,
}

static LIB: OnceLock<Option<DistConfLib>> = OnceLock::new();

pub fn get_lib() -> Option<&'static DistConfLib> {
    LIB.get_or_init(|| {
        let lib_path = std::env::var("LIBDISTCONF_PATH")
            .unwrap_or_else(|_| "../../distributed-config/release/libdistconf.so".to_string());
        
        unsafe {
            let lib = Library::new(lib_path).ok()?;
            Some(DistConfLib {
                dist_conf_new: std::mem::transmute::<Symbol<'_, extern "C" fn(*const c_char) -> usize>, Symbol<'static, extern "C" fn(*const c_char) -> usize>>(lib.get::<extern "C" fn(*const c_char) -> usize>(b"DistConf_New").ok()?),
                dist_conf_close: std::mem::transmute::<Symbol<'_, extern "C" fn(usize)>, Symbol<'static, extern "C" fn(usize)>>(lib.get::<extern "C" fn(usize)>(b"DistConf_Close").ok()?),
                dist_conf_get: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, *const c_char, *const c_char) -> *mut c_char>, Symbol<'static, extern "C" fn(usize, *const c_char, *const c_char) -> *mut c_char>>(lib.get::<extern "C" fn(usize, *const c_char, *const c_char) -> *mut c_char>(b"DistConf_Get").ok()?),
                dist_conf_set: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, *const c_char, *const c_char, *const c_char) -> bool>, Symbol<'static, extern "C" fn(usize, *const c_char, *const c_char, *const c_char) -> bool>>(lib.get::<extern "C" fn(usize, *const c_char, *const c_char, *const c_char) -> bool>(b"DistConf_Set").ok()?),
                dist_conf_sync: std::mem::transmute::<Symbol<'_, extern "C" fn(usize) -> c_int>, Symbol<'static, extern "C" fn(usize) -> c_int>>(lib.get::<extern "C" fn(usize) -> c_int>(b"DistConf_Sync").ok()?),
                dist_conf_on_live_conf_update: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, ConfigUpdateCb)>, Symbol<'static, extern "C" fn(usize, ConfigUpdateCb)>>(lib.get::<extern "C" fn(usize, ConfigUpdateCb)>(b"DistConf_OnLiveConfUpdate").ok()?),
                dist_conf_on_registry_update: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, ConfigUpdateCb)>, Symbol<'static, extern "C" fn(usize, ConfigUpdateCb)>>(lib.get::<extern "C" fn(usize, ConfigUpdateCb)>(b"DistConf_OnRegistryUpdate").ok()?),
                dist_conf_get_address: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, *const c_char) -> *mut c_char>, Symbol<'static, extern "C" fn(usize, *const c_char) -> *mut c_char>>(lib.get::<extern "C" fn(usize, *const c_char) -> *mut c_char>(b"DistConf_GetAddress").ok()?),
                dist_conf_get_grpc_address: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, *const c_char) -> *mut c_char>, Symbol<'static, extern "C" fn(usize, *const c_char) -> *mut c_char>>(lib.get::<extern "C" fn(usize, *const i8) -> *mut i8>(b"DistConf_GetGRPCAddress").ok()?),
                dist_conf_get_capability: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, *const c_char) -> *mut c_char>, Symbol<'static, extern "C" fn(usize, *const c_char) -> *mut c_char>>(lib.get::<extern "C" fn(usize, *const c_char) -> *mut c_char>(b"DistConf_GetCapability").ok()?),
                dist_conf_get_full_config: std::mem::transmute::<Symbol<'_, extern "C" fn(usize) -> *mut c_char>, Symbol<'static, extern "C" fn(usize) -> *mut c_char>>(lib.get::<extern "C" fn(usize) -> *mut c_char>(b"DistConf_GetFullConfig").ok()?),
                dist_conf_get_last_error: std::mem::transmute::<Symbol<'_, unsafe extern "C" fn() -> *const c_char>, Symbol<'static, unsafe extern "C" fn() -> *const c_char>>(lib.get::<unsafe extern "C" fn() -> *const c_char>(b"DistConf_GetLastError").ok()?),
                dist_conf_decrypt: std::mem::transmute::<Symbol<'_, unsafe extern "C" fn(usize, *const c_char) -> *const c_char>, Symbol<'static, unsafe extern "C" fn(usize, *const c_char) -> *const c_char>>(lib.get::<unsafe extern "C" fn(usize, *const c_char) -> *const c_char>(b"DistConf_Decrypt").ok()?),
                dist_conf_share_config: std::mem::transmute::<Symbol<'_, extern "C" fn(usize, *const c_char) -> bool>, Symbol<'static, extern "C" fn(usize, *const c_char) -> bool>>(lib.get::<extern "C" fn(usize, *const c_char) -> bool>(b"DistConf_ShareConfig").ok()?),
                dist_conf_free_string: std::mem::transmute::<Symbol<'_, extern "C" fn(*mut c_char)>, Symbol<'static, extern "C" fn(*mut c_char)>>(lib.get::<extern "C" fn(*mut c_char)>(b"DistConf_FreeString").ok()?),
                _lib: lib,
            })
        }
    }).as_ref()
}

/// Converts a C string pointer to a Rust String and frees the C string.
///
/// # Safety
///
/// * `c_ptr` must be a valid, null-terminated C string.
/// * `c_ptr` must have been allocated by the `dist_conf` library as it will be freed
///   using `dist_conf_free_string`.
/// * After calling this function, `c_ptr` must not be used again.
pub unsafe fn to_rust_string(c_ptr: *mut c_char) -> Option<String> {
    if c_ptr.is_null() {
        return None;
    }
    let lib = get_lib()?;
    unsafe {
        let s = CStr::from_ptr(c_ptr).to_string_lossy().into_owned();
        (lib.dist_conf_free_string)(c_ptr);
        Some(s)
    }
}
