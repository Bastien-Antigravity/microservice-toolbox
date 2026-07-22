#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Locates and loads the shared C library (libunilog) into the Python process via ctypes.
Enables high-performance logging and configuration management.
"""

import ctypes
from ctypes import CDLL, CFUNCTYPE, c_char_p, c_int, c_size_t, c_longlong, c_void_p
from os import getenv as osGetenv
from os.path import exists as osPathExists
from pathlib import Path
import sys

# Define the callback type matching the C header: typedef void (*config_update_cb)(GoUintptr handle, const char* json_data);
CALLBACK_TYPE = CFUNCTYPE(None, c_char_p)


def load_libunilog() -> ctypes.CDLL:
    """
    Locates and loads the libunilog shared library.
    Returns a ctypes.CDLL handle or None if not found.
    """
    lib_name = "libunilog"
    
    # 1. Try environment variable
    lib_path = osGetenv("LIBUNILOG_PATH") or osGetenv("LIBDISTCONF_PATH")

    if not lib_path:
        # 2. Check platform-specific extensions in relative workspace locations
        ext = ".dylib" if sys.platform == "darwin" else (".dll" if sys.platform == "win32" else ".so")
        
        possible_paths = [
            f"./{lib_name}{ext}",
            f"/usr/local/lib/{lib_name}{ext}",
            # Relative path if running in the workspace
            f"../../universal-logger/unilog/libunilog/{lib_name}{ext}",
            f"../universal-logger/unilog/libunilog/{lib_name}{ext}",
        ]
        
        # Check standard python site-packages / package sibling locations
        current_dir = Path(__file__).resolve().parent
        search_roots = [current_dir, current_dir.parent.parent, current_dir.parent.parent.parent]
        
        # Also check the active virtualenv's site-packages (editable installs resolve to source, not venv)
        if hasattr(sys, 'prefix') and sys.prefix != sys.base_prefix:
            _venv_sp = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
            if _venv_sp.exists():
                search_roots.append(_venv_sp)

        for root in search_roots:
            possible_paths.append(str(root / "unilog" / f"{lib_name}{ext}"))
            possible_paths.append(str(root / "unilog" / "libunilog" / f"{lib_name}{ext}"))
            possible_paths.append(str(root / "libunilog" / f"{lib_name}{ext}"))
            possible_paths.append(str(root / "universal-logger" / "unilog" / "libunilog" / f"{lib_name}{ext}"))
            possible_paths.append(str(root / "universal-logger" / "unilog" / "python" / "unilog" / f"{lib_name}{ext}"))

        for p in possible_paths:
            if osPathExists(p):
                lib_path = p
                break

    if not lib_path:
        # Fallback to finding it on system path
        try:
            from ctypes.util import find_library
            res = find_library(lib_name)
            if res:
                lib_path = res
        except Exception:
            pass

    if not lib_path:
        return None

    try:
        lib_handle = ctypes.CDLL(str(lib_path))

        # Define function signatures matching UniLog standards
        lib_handle.UniLog_Init.argtypes = [
            c_char_p, c_char_p, c_char_p, 
            c_int, c_int, c_size_t
        ]
        lib_handle.UniLog_Init.restype = c_size_t
        lib_handle.UniLog_Close.argtypes = [c_size_t]

        lib_handle.UniLog_LogWithMetadata.argtypes = [
            c_size_t, c_longlong, c_char_p, 
            c_char_p, c_char_p, c_char_p, c_char_p
        ]
        lib_handle.UniLog_SetLevel.argtypes = [c_size_t, c_longlong]
        lib_handle.UniLog_GetLevel.argtypes = [c_size_t]
        lib_handle.UniLog_GetLevel.restype = c_int

        lib_handle.UniLog_AddMetadata.argtypes = [c_size_t, c_char_p, c_char_p]
        lib_handle.UniLog_SetMetadata.argtypes = [c_size_t, c_char_p]

        lib_handle.DistConf_FreeString.argtypes = [c_void_p]
        lib_handle.UniLog_Config_Get.argtypes = [c_size_t, c_char_p, c_char_p]
        lib_handle.UniLog_Config_Get.restype = c_void_p
        lib_handle.UniLog_Config_Set.argtypes = [c_size_t, c_char_p, c_char_p, c_char_p]
        lib_handle.UniLog_OnConfigUpdate.argtypes = [c_size_t, CALLBACK_TYPE]
        lib_handle.UniLog_RegisterNotifCallback.argtypes = [c_size_t, CALLBACK_TYPE]

        # Compatibility layer functions for old config tools
        try:
            lib_handle.DistConf_New.argtypes = [c_char_p]
            lib_handle.DistConf_New.restype = c_size_t
            lib_handle.DistConf_Get.argtypes = [c_size_t, c_char_p, c_char_p]
            lib_handle.DistConf_Get.restype = c_void_p
            lib_handle.DistConf_Set.argtypes = [c_size_t, c_char_p, c_char_p, c_char_p]
            lib_handle.DistConf_GetFullConfig.argtypes = [c_size_t]
            lib_handle.DistConf_GetFullConfig.restype = c_void_p
            lib_handle.DistConf_Close.argtypes = [c_size_t]
        except Exception:
            pass

        return lib_handle
    except Exception as e:
        print(f"Failed to load libunilog library: {e}", file=sys.stderr)
        return None


# Singleton instance
lib = load_libunilog()
