#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Locates and loads the shared C library (libdistconf) into the Python process via ctypes.
Enables high-performance configuration management and cross-language interoperability.

DATA FLOW:
1. Scans environment variables and common filesystem paths for the binary.
2. Loads the shared object (.so/.dylib) using ctypes.
3. Defines C-compatible function signatures for the distributed-config engine.

KEY PARAMETERS:
- LIBDISTCONF_PATH: Environment variable to override the library search path.
"""

import ctypes
from ctypes import CFUNCTYPE, c_char_p, c_void_p
from os import getenv as osGetenv
from os.path import exists as osPathExists

# -----------------------------------------------------------------------------------------------

# Define the callback type matching the C header: typedef void (*config_update_cb)(GoUintptr handle, const char* json_data);
CALLBACK_TYPE = CFUNCTYPE(None, c_void_p, c_char_p)

# -----------------------------------------------------------------------------------------------


def load_libdistconf():
    """
    Locates and loads the libdistconf shared library.
    Returns a ctypes.CDLL handle or None if not found.
    """
    # 1. Try environment variable
    lib_path = osGetenv("LIBDISTCONF_PATH")

    if not lib_path:
        # 2. Try common locations
        possible_paths = [
            "./libdistconf.so",
            "./libdistconf.dylib",
            "/usr/local/lib/libdistconf.so",
            # Add relative path from toolbox to distributed-config bridge if in same workspace
            "../../distributed-config/distconf/libdistconf/libdistconf.so",
            "../../distributed-config/distconf/libdistconf/libdistconf.dylib",
        ]
        for p in possible_paths:
            if osPathExists(p):
                lib_path = p
                break

    if not lib_path:
        return None

    try:
        lib_handle = ctypes.CDLL(lib_path)

        # Define function signatures matching v0.0.1 standard
        lib_handle.DistConf_New.argtypes = [c_char_p]
        lib_handle.DistConf_New.restype = c_void_p

        lib_handle.DistConf_Close.argtypes = [c_void_p]
        lib_handle.DistConf_Close.restype = None

        lib_handle.DistConf_Get.argtypes = [c_void_p, c_char_p, c_char_p]
        lib_handle.DistConf_Get.restype = c_char_p

        lib_handle.DistConf_Set.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
        lib_handle.DistConf_Set.restype = ctypes.c_bool

        lib_handle.DistConf_Sync.argtypes = [c_void_p]
        lib_handle.DistConf_Sync.restype = ctypes.c_int

        lib_handle.DistConf_OnLiveConfUpdate.argtypes = [c_void_p, CALLBACK_TYPE]
        lib_handle.DistConf_OnLiveConfUpdate.restype = None

        lib_handle.DistConf_GetLastError.argtypes = []
        lib_handle.DistConf_GetLastError.restype = c_char_p

        lib_handle.DistConf_OnRegistryUpdate.argtypes = [c_void_p, CALLBACK_TYPE]
        lib_handle.DistConf_OnRegistryUpdate.restype = None

        lib_handle.DistConf_GetAddress.argtypes = [c_void_p, c_char_p]
        lib_handle.DistConf_GetAddress.restype = c_char_p

        lib_handle.DistConf_GetGRPCAddress.argtypes = [c_void_p, c_char_p]
        lib_handle.DistConf_GetGRPCAddress.restype = c_char_p

        lib_handle.DistConf_GetCapability.argtypes = [c_void_p, c_char_p]
        lib_handle.DistConf_GetCapability.restype = c_char_p

        lib_handle.DistConf_GetFullConfig.argtypes = [c_void_p]
        lib_handle.DistConf_GetFullConfig.restype = c_char_p

        lib_handle.DistConf_Decrypt.argtypes = [c_void_p, c_char_p]
        lib_handle.DistConf_Decrypt.restype = c_char_p

        lib_handle.DistConf_ShareConfig.argtypes = [c_void_p, c_char_p]
        lib_handle.DistConf_ShareConfig.restype = ctypes.c_bool

        lib_handle.DistConf_FreeString.argtypes = [c_char_p]
        lib_handle.DistConf_FreeString.restype = None

        return lib_handle
    except Exception as e:
        print(f"Failed to load libdistconf: {e}")
        return None


# -----------------------------------------------------------------------------------------------

# Singleton instance
lib = load_libdistconf()
