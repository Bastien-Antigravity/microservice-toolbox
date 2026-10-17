#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Dynamic shared library loader and CGO bridge initializer for microservice-toolbox.
Resolves cross-platform binary paths (.dylib, .so, .dll) across repository layouts,
virtualenv site-packages, and fallback search paths with strict ABI typing.

DATA FLOW:
1. Input: Library identifier string ("libunilog", "libdistconf", "libnotif").
2. Logic: Priority search across explicit environment overrides -> active workspace
   roots -> venv site-packages -> OS dynamic loader fallbacks.
3. Output: Fully typed ctypesCDLL handles with standardized C ABI function signatures.

KEY PARAMETERS:
- LIBUNILOG_PATH: Environment variable overriding the libunilog binary search path.
- LIBDISTCONF_PATH: Environment variable overriding the libdistconf binary search path.
"""

from ctypes import (
    CDLL as ctypesCDLL,
    CFUNCTYPE,
    c_bool,
    c_char_p,
    c_double as ctypesC_double,
    c_int,
    c_longlong,
    c_size_t,
    c_void_p,
)
from ctypes.util import find_library as ctypesFindLibrary
from os import getenv as osGetenv
from os.path import exists as osPathExists
from pathlib import Path
from shutil import which as shutilWhich
from subprocess import run as subprocessRun
from sys import (
    base_prefix as sysBasePrefix,
    platform as sysPlatform,
    prefix as sysPrefix,
    stderr as sysStderr,
    version_info as sysVersionInfo,
)
from typing import List, Optional

# -----------------------------------------------------------------------------------------------
# Callback Types matching C Header Signatures
# -----------------------------------------------------------------------------------------------

# typedef void (*config_update_cb)(GoUintptr handle, const char* json_data);
CONFIG_CALLBACK_TYPE = CFUNCTYPE(None, c_void_p, c_char_p)

# typedef void (*logger_callback_cb)(const char* json_data);
LOGGER_CALLBACK_TYPE = CFUNCTYPE(None, c_char_p)

# Generic callback alias for backward compatibility
CALLBACK_TYPE = CONFIG_CALLBACK_TYPE

# -----------------------------------------------------------------------------------------------
# Dynamic Shared Library Discovery Engine
# -----------------------------------------------------------------------------------------------


def get_platform_extension() -> str:
    """Returns the OS-specific dynamic library file extension."""
    if sysPlatform == "darwin":
        return ".dylib"
    elif sysPlatform == "win32":
        return ".dll"
    return ".so"


def resolve_library_path(lib_name: str, env_var: Optional[str] = None) -> Optional[str]:
    """
    Resolves the absolute path to a named dynamic library (e.g. 'libunilog', 'libdistconf').
    Checks explicit environment overrides first, followed by workspace roots, virtualenv
    site-packages, local sibling directories, and OS library search paths.
    """
    # 1. Explicit environment variable override
    if env_var:
        env_val = osGetenv(env_var)
        if env_val and osPathExists(env_val):
            return str(Path(env_val).resolve())

    ext = get_platform_extension()
    filename = f"{lib_name}{ext}"

    # 2. Discover workspace root and repository root relative to this file
    # Path: microservice-toolbox/python/microservice_toolbox/utils/lib_loader.py
    current_dir = Path(__file__).resolve().parent
    toolbox_root = current_dir.parent.parent.parent
    workspace_root = toolbox_root.parent

    candidate_paths: List[Path] = [
        # Explicit package-internal vendor directories
        current_dir / filename,
        current_dir.parent / filename,
        current_dir.parent / "lib" / filename,

        # Microservice Toolbox root and subdirectories
        toolbox_root / filename,
        toolbox_root / "lib" / filename,
        toolbox_root / "bin" / filename,

        # Standard multi-repo sibling workspaces
        workspace_root / "universal-logger" / "libunilog" / filename,
        workspace_root / "universal-logger" / "unilog" / "libunilog" / filename,
        workspace_root / "universal-logger" / "unilog" / "python" / "unilog" / filename,
        workspace_root / "universal-logger" / "bin" / filename,
        workspace_root / "distributed-config" / "distconf" / "libdistconf" / filename,
        workspace_root / "distributed-config" / "distconf" / "python" / "distconf" / filename,
        workspace_root / "distributed-config" / "bin" / filename,
        workspace_root / "notif-server" / "notif" / "libnotif" / filename,
        workspace_root / "notif-server" / "notif" / "python" / "notif" / filename,
        workspace_root / "notif-server" / "bin" / filename,
    ]

    # Check parent directories for monolithic or umbrella checkouts
    for parent in [current_dir] + list(current_dir.parents):
        if (parent / ".git").exists() or (parent / "docker-compose.yaml").exists():
            if lib_name == "libunilog":
                candidate_paths.append(parent / "universal-logger" / "libunilog" / filename)
                candidate_paths.append(parent / "universal-logger" / "unilog" / "libunilog" / filename)
                candidate_paths.append(parent / "universal-logger" / "unilog" / "python" / "unilog" / filename)
            elif lib_name == "libdistconf":
                candidate_paths.append(parent / "distributed-config" / "distconf" / "libdistconf" / filename)
                candidate_paths.append(parent / "distributed-config" / "distconf" / "python" / "distconf" / filename)
            elif lib_name == "libnotif":
                candidate_paths.append(parent / "notif-server" / "notif" / "libnotif" / filename)
                candidate_paths.append(parent / "notif-server" / "notif" / "python" / "notif" / filename)
            break

    # Virtualenv site-packages check (active venv or nearest venv)
    if hasattr(sysPrefix, "lower") and sysPrefix != sysBasePrefix:
        venv_sp = Path(sysPrefix) / "lib" / f"python{sysVersionInfo.major}.{sysVersionInfo.minor}" / "site-packages"
        if venv_sp.exists():
            candidate_paths.extend([
                venv_sp / "unilog" / filename,
                venv_sp / "distconf" / filename,
                venv_sp / "notif" / filename,
                venv_sp / filename,
            ])

    # 3. Evaluate candidate paths in order of preference
    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate.resolve())

    # 4. Fallback to OS library lookup via ctypesFindLibrary
    try:
        os_lib = ctypesFindLibrary(lib_name)
        if os_lib and osPathExists(os_lib):
            return str(Path(os_lib).resolve())
    except Exception:
        pass

    # 5. On-demand compilation fallback for fresh local clones
    autobuilt = _try_autobuild_library(lib_name)
    if autobuilt:
        return autobuilt

    return None


def _try_autobuild_library(lib_name: str) -> Optional[str]:
    """
    Auto-compiles missing CGO shared libraries on-the-fly during fresh local installs
    if the Go compiler and repository source trees are present.
    """
    if not shutilWhich("go"):
        return None

    ext = get_platform_extension()
    filename = f"{lib_name}{ext}"
    current_dir = Path(__file__).resolve().parent
    toolbox_root = current_dir.parent.parent.parent
    workspace_root = toolbox_root.parent

    target_file = None
    src_dir = None

    if lib_name == "libunilog":
        src_dir = workspace_root / "universal-logger" / "src" / "cgo_bridge"
        target_dir = workspace_root / "universal-logger" / "libunilog"
        target_file = target_dir / filename
    elif lib_name == "libdistconf":
        src_dir = workspace_root / "distributed-config" / "cmd" / "libdistconf"
        target_dir = workspace_root / "distributed-config" / "distconf" / "libdistconf"
        target_file = target_dir / filename
    elif lib_name == "libnotif":
        src_dir = workspace_root / "notif-server" / "cmd" / "libnotif"
        target_dir = workspace_root / "notif-server" / "notif" / "libnotif"
        target_file = target_dir / filename

    if src_dir and src_dir.exists():
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            print(f"[lib_loader] On-demand compiling {lib_name} ({filename}) for fresh install...", file=sysStderr)
            cmd = ["go", "build", "-buildmode=c-shared", "-o", str(target_file), "."]
            res = subprocessRun(cmd, cwd=str(src_dir), capture_output=True, text=True, timeout=45)
            if res.returncode == 0 and target_file.exists():
                if sysPlatform == "darwin" and shutilWhich("install_name_tool"):
                    subprocessRun(["install_name_tool", "-id", f"@rpath/{filename}", str(target_file)], capture_output=True)
                print(f"[lib_loader] Successfully compiled {filename} at {target_file}", file=sysStderr)
                return str(target_file.resolve())
            else:
                print(f"[lib_loader] Compilation of {lib_name} failed: {res.stderr}", file=sysStderr)
        except Exception as e:
            print(f"[lib_loader] Auto-build exception for {lib_name}: {e}", file=sysStderr)

    return None


# -----------------------------------------------------------------------------------------------
# UniLog Shared Library Loader & FFI Signatures
# -----------------------------------------------------------------------------------------------

_unilog_handle: Optional[ctypesCDLL] = None


def load_libunilog() -> Optional[ctypesCDLL]:
    """
    Locates and loads the libunilog shared library.
    Defines full C ABI function signatures and returns a ctypesCDLL handle.
    """
    global _unilog_handle
    if _unilog_handle is not None:
        return _unilog_handle

    lib_path = resolve_library_path("libunilog", "LIBUNILOG_PATH")
    if not lib_path:
        return None

    try:
        handle = ctypesCDLL(lib_path)

        # Core UniLog signatures
        handle.UniLog_Init.argtypes = [c_char_p, c_char_p, c_char_p, c_int, c_int, c_size_t]
        handle.UniLog_Init.restype = c_size_t

        handle.UniLog_Close.argtypes = [c_size_t]
        handle.UniLog_Close.restype = None

        handle.UniLog_LogWithMetadata.argtypes = [c_size_t, c_longlong, c_char_p, c_char_p, c_char_p, c_char_p, c_char_p]
        handle.UniLog_LogWithMetadata.restype = None

        handle.UniLog_SetLevel.argtypes = [c_size_t, c_longlong]
        handle.UniLog_SetLevel.restype = None

        handle.UniLog_GetLevel.argtypes = [c_size_t]
        handle.UniLog_GetLevel.restype = c_int

        handle.UniLog_AddMetadata.argtypes = [c_size_t, c_char_p, c_char_p]
        handle.UniLog_AddMetadata.restype = None

        handle.UniLog_SetMetadata.argtypes = [c_size_t, c_char_p]
        handle.UniLog_SetMetadata.restype = None

        handle.DistConf_FreeString.argtypes = [c_void_p]
        handle.DistConf_FreeString.restype = None

        handle.UniLog_Config_Get.argtypes = [c_size_t, c_char_p, c_char_p]
        handle.UniLog_Config_Get.restype = c_void_p

        handle.UniLog_Config_Set.argtypes = [c_size_t, c_char_p, c_char_p, c_char_p]
        handle.UniLog_Config_Set.restype = c_int

        handle.UniLog_OnConfigUpdate.argtypes = [c_size_t, LOGGER_CALLBACK_TYPE]
        handle.UniLog_OnConfigUpdate.restype = None

        handle.UniLog_RegisterNotifCallback.argtypes = [c_size_t, LOGGER_CALLBACK_TYPE]
        handle.UniLog_RegisterNotifCallback.restype = None

        # Bind DistConf symbols if present on consolidated library
        _bind_distconf_signatures(handle)

        _unilog_handle = handle
        return _unilog_handle
    except Exception as e:
        print(f"Failed to load libunilog library ({lib_path}): {e}", file=sysStderr)
        return None


# -----------------------------------------------------------------------------------------------
# DistConf Shared Library Loader & FFI Signatures
# -----------------------------------------------------------------------------------------------

_distconf_handle: Optional[ctypesCDLL] = None


def _bind_distconf_signatures(handle: ctypesCDLL) -> None:
    """Binds standard DistConf function signatures to a ctypesCDLL handle safely."""
    try:
        handle.DistConf_New.argtypes = [c_char_p]
        handle.DistConf_New.restype = c_void_p

        handle.DistConf_Close.argtypes = [c_void_p]
        handle.DistConf_Close.restype = None

        handle.DistConf_Get.argtypes = [c_void_p, c_char_p, c_char_p]
        handle.DistConf_Get.restype = c_char_p

        handle.DistConf_Set.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
        handle.DistConf_Set.restype = c_bool

        handle.DistConf_Sync.argtypes = [c_void_p]
        handle.DistConf_Sync.restype = c_int

        handle.DistConf_OnLiveConfUpdate.argtypes = [c_void_p, CONFIG_CALLBACK_TYPE]
        handle.DistConf_OnLiveConfUpdate.restype = None

        handle.DistConf_GetLastError.argtypes = []
        handle.DistConf_GetLastError.restype = c_char_p

        handle.DistConf_OnRegistryUpdate.argtypes = [c_void_p, CONFIG_CALLBACK_TYPE]
        handle.DistConf_OnRegistryUpdate.restype = None

        handle.DistConf_GetAddress.argtypes = [c_void_p, c_char_p]
        handle.DistConf_GetAddress.restype = c_char_p

        handle.DistConf_GetGRPCAddress.argtypes = [c_void_p, c_char_p]
        handle.DistConf_GetGRPCAddress.restype = c_char_p

        handle.DistConf_GetRESTAddress.argtypes = [c_void_p, c_char_p]
        handle.DistConf_GetRESTAddress.restype = c_char_p

        handle.DistConf_GetCapability.argtypes = [c_void_p, c_char_p]
        handle.DistConf_GetCapability.restype = c_char_p

        handle.DistConf_GetFullConfig.argtypes = [c_void_p]
        handle.DistConf_GetFullConfig.restype = c_char_p

        handle.DistConf_Decrypt.argtypes = [c_void_p, c_char_p]
        handle.DistConf_Decrypt.restype = c_char_p

        handle.DistConf_ApplyFileOverride.argtypes = [c_void_p, c_char_p]
        handle.DistConf_ApplyFileOverride.restype = c_char_p

        handle.DistConf_ShareConfig.argtypes = [c_void_p, c_char_p]
        handle.DistConf_ShareConfig.restype = c_bool

        handle.DistConf_FreeString.argtypes = [c_char_p]
        handle.DistConf_FreeString.restype = None
    except AttributeError:
        # Not all shared libraries may contain all symbols (e.g. standalone non-consolidated)
        pass


def load_libdistconf() -> Optional[ctypesCDLL]:
    """
    Locates and loads the libdistconf shared library.
    On macOS, if libunilog is available, reuses its handle to avoid dual Go CGO runtime collisions.
    Defines full C ABI function signatures and returns a ctypesCDLL handle.
    """
    global _distconf_handle
    if _distconf_handle is not None:
        return _distconf_handle

    # On macOS, reuse the consolidated libunilog handle if it already exports DistConf
    if sysPlatform == "darwin":
        unilog = load_libunilog()
        if unilog and hasattr(unilog, "DistConf_GetRESTAddress"):
            _distconf_handle = unilog
            return _distconf_handle

    # Otherwise resolve dedicated libdistconf or explicit LIBDISTCONF_PATH
    lib_path = resolve_library_path("libdistconf", "LIBDISTCONF_PATH")
    if not lib_path and sysPlatform == "darwin":
        lib_path = resolve_library_path("libunilog", "LIBUNILOG_PATH")

    if not lib_path:
        return None

    try:
        handle = ctypesCDLL(lib_path)
        _bind_distconf_signatures(handle)
        _distconf_handle = handle
        return _distconf_handle
    except Exception as e:
        print(f"Failed to load libdistconf ({lib_path}): {e}", file=sysStderr)
        return None


# -----------------------------------------------------------------------------------------------
# Notif Shared Library Loader & FFI Signatures
# -----------------------------------------------------------------------------------------------

_notif_handle: Optional[ctypesCDLL] = None


def load_libnotif() -> Optional[ctypesCDLL]:
    """
    Locates and loads the libnotif shared library from notif-server.
    Defines full C ABI function signatures and returns a ctypesCDLL handle.
    """
    global _notif_handle
    if _notif_handle is not None:
        return _notif_handle

    lib_path = resolve_library_path("libnotif", "LIBNOTIF_PATH")
    if not lib_path:
        return None

    try:
        handle = ctypesCDLL(lib_path)

        handle.Notif_Send.argtypes = [c_char_p, c_char_p, c_char_p, c_char_p, c_char_p]
        handle.Notif_Send.restype = c_int

        handle.Notif_SendWithTimeout.argtypes = [c_char_p, c_char_p, c_char_p, c_char_p, c_char_p, ctypesC_double]
        handle.Notif_SendWithTimeout.restype = c_int

        handle.Notif_GetLastError.argtypes = []
        handle.Notif_GetLastError.restype = c_void_p

        handle.Notif_FreeString.argtypes = [c_void_p]
        handle.Notif_FreeString.restype = None

        handle.Notif_Close.argtypes = []
        handle.Notif_Close.restype = None

        _notif_handle = handle
        return _notif_handle
    except Exception as e:
        print(f"Failed to load libnotif ({lib_path}): {e}", file=sysStderr)
        return None
