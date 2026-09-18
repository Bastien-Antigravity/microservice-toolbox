#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unified single source of truth for dynamic CGO shared library discovery and loading
(libunilog and libdistconf) into Python processes across the Bastien-Antigravity ecosystem.

DATA FLOW:
1. Input: Environment variables (LIBUNILOG_PATH, LIBDISTCONF_PATH) or workspace filesystem layout.
2. Logic: Systematically resolves candidate paths (local, workspace roots, virtualenvs, system).
          On macOS, shares the consolidated libunilog handle to prevent dual Go runtime collisions.
3. Output: Fully typed ctypes.CDLL handles with standardized C ABI function signatures.

KEY PARAMETERS:
- LIBUNILOG_PATH: Environment variable overriding the libunilog binary search path.
- LIBDISTCONF_PATH: Environment variable overriding the libdistconf binary search path.
"""

import ctypes
from ctypes import CDLL, CFUNCTYPE, c_bool, c_char_p, c_int, c_longlong, c_size_t, c_void_p
import os
from pathlib import Path
import sys
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
    if sys.platform == "darwin":
        return ".dylib"
    elif sys.platform == "win32":
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
        env_val = os.getenv(env_var)
        if env_val and os.path.exists(env_val):
            return str(Path(env_val).resolve())

    ext = get_platform_extension()
    filename = f"{lib_name}{ext}"

    # 2. Discover workspace root and repository root relative to this file
    # Path: microservice-toolbox/python/microservice_toolbox/utils/lib_loader.py
    current_dir = Path(__file__).resolve().parent
    toolbox_root = current_dir.parent.parent.parent  # microservice-toolbox
    workspace_root = toolbox_root.parent             # Bastien-Antigravity

    candidate_paths: List[Path] = [
        # Relative to current working directory
        Path(f"./{filename}"),
        Path(f"/usr/local/lib/{filename}"),
    ]

    # Workspace-specific locations based on library
    if lib_name == "libunilog":
        candidate_paths.extend([
            workspace_root / "universal-logger" / "unilog" / "libunilog" / filename,
            workspace_root / "universal-logger" / "unilog" / "python" / "unilog" / filename,
            workspace_root / "universal-logger" / "libunilog" / filename,
            toolbox_root / "python" / "microservice_toolbox" / "logger" / filename,
        ])
    elif lib_name == "libdistconf":
        candidate_paths.extend([
            workspace_root / "distributed-config" / "distconf" / "libdistconf" / filename,
            workspace_root / "distributed-config" / "distconf" / "python" / "distconf" / filename,
            workspace_root / "distributed-config" / "bin" / filename,
            toolbox_root / "python" / "microservice_toolbox" / "config" / filename,
        ])

    # Sibling directory check (if current working directory is another microservice)
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "universal-logger").is_dir():
            if lib_name == "libunilog":
                candidate_paths.append(parent / "universal-logger" / "unilog" / "libunilog" / filename)
                candidate_paths.append(parent / "universal-logger" / "unilog" / "python" / "unilog" / filename)
            elif lib_name == "libdistconf":
                candidate_paths.append(parent / "distributed-config" / "distconf" / "libdistconf" / filename)
                candidate_paths.append(parent / "distributed-config" / "distconf" / "python" / "distconf" / filename)
            break

    # Virtualenv site-packages check (active venv or nearest venv)
    if hasattr(sys, "prefix") and sys.prefix != sys.base_prefix:
        venv_sp = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        if venv_sp.exists():
            candidate_paths.extend([
                venv_sp / "unilog" / filename,
                venv_sp / "distconf" / filename,
                venv_sp / filename,
            ])

    # 3. Evaluate candidate paths in order of preference
    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate.resolve())

    # 4. Fallback to OS library lookup via ctypes.util.find_library
    try:
        from ctypes.util import find_library
        os_lib = find_library(lib_name)
        if os_lib and os.path.exists(os_lib):
            return str(Path(os_lib).resolve())
    except Exception:
        pass

    return None


# -----------------------------------------------------------------------------------------------
# UniLog Shared Library Loader & FFI Signatures
# -----------------------------------------------------------------------------------------------

_unilog_handle: Optional[ctypes.CDLL] = None


def load_libunilog() -> Optional[ctypes.CDLL]:
    """
    Locates and loads the libunilog shared library.
    Defines full C ABI function signatures and returns a ctypes.CDLL handle.
    """
    global _unilog_handle
    if _unilog_handle is not None:
        return _unilog_handle

    lib_path = resolve_library_path("libunilog", "LIBUNILOG_PATH")
    if not lib_path:
        return None

    try:
        handle = ctypes.CDLL(lib_path)

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
        print(f"Failed to load libunilog library ({lib_path}): {e}", file=sys.stderr)
        return None


# -----------------------------------------------------------------------------------------------
# DistConf Shared Library Loader & FFI Signatures
# -----------------------------------------------------------------------------------------------

_distconf_handle: Optional[ctypes.CDLL] = None


def _bind_distconf_signatures(handle: ctypes.CDLL) -> None:
    """Binds standard DistConf function signatures to a ctypes.CDLL handle safely."""
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


def load_libdistconf() -> Optional[ctypes.CDLL]:
    """
    Locates and loads the libdistconf shared library.
    On macOS, if libunilog is available, reuses its handle to avoid dual Go CGO runtime collisions.
    Defines full C ABI function signatures and returns a ctypes.CDLL handle.
    """
    global _distconf_handle
    if _distconf_handle is not None:
        return _distconf_handle

    # On macOS, reuse the consolidated libunilog handle if it already exports DistConf
    if sys.platform == "darwin":
        unilog = load_libunilog()
        if unilog and hasattr(unilog, "DistConf_GetRESTAddress"):
            _distconf_handle = unilog
            return _distconf_handle

    # Otherwise resolve dedicated libdistconf or explicit LIBDISTCONF_PATH
    lib_path = resolve_library_path("libdistconf", "LIBDISTCONF_PATH")
    if not lib_path and sys.platform == "darwin":
        lib_path = resolve_library_path("libunilog", "LIBUNILOG_PATH")

    if not lib_path:
        return None

    try:
        handle = ctypes.CDLL(lib_path)
        _bind_distconf_signatures(handle)
        _distconf_handle = handle
        return _distconf_handle
    except Exception as e:
        print(f"Failed to load libdistconf ({lib_path}): {e}", file=sys.stderr)
        return None
