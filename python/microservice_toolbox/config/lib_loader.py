#!/usr/bin/env python
# coding:utf-8

import os
import ctypes
from ctypes import c_char_p, c_void_p, CFUNCTYPE

# -----------------------------------------------------------------------------------------------

# Define the callback type matching the C header: typedef void (*config_update_cb)(GoUintptr handle, const char* json_data);
CALLBACK_TYPE = CFUNCTYPE(None, c_void_p, c_char_p)

# -----------------------------------------------------------------------------------------------

def load_libdistconf():
    """
    Locates and loads the libdistconf shared library.
    """
    # 1. Try environment variable
    lib_path = os.getenv("LIBDISTCONF_PATH")
    
    if not lib_path:
        # 2. Try common locations
        possible_paths = [
            "./libdistconf.so",
            "./libdistconf.dylib",
            "/usr/local/lib/libdistconf.so",
            # Add relative path from toolbox to distributed-config release if in same workspace
            "../../distributed-config/release/libdistconf.so"
        ]
        for p in possible_paths:
            if os.path.exists(p):
                lib_path = p
                break
                
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)
        
        # Define function signatures matching v1.9.8 standard
        lib.DistConf_New.argtypes = [c_char_p]
        lib.DistConf_New.restype = c_void_p
        
        lib.DistConf_Close.argtypes = [c_void_p]
        lib.DistConf_Close.restype = None
        
        lib.DistConf_Get.argtypes = [c_void_p, c_char_p, c_char_p]
        lib.DistConf_Get.restype = c_char_p
        
        lib.DistConf_Set.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
        lib.DistConf_Set.restype = ctypes.c_bool
        
        lib.DistConf_Sync.argtypes = [c_void_p]
        lib.DistConf_Sync.restype = ctypes.c_int
        
        lib.DistConf_OnLiveConfUpdate.argtypes = [c_void_p, CALLBACK_TYPE]
        lib.DistConf_OnLiveConfUpdate.restype = None

        lib.DistConf_OnRegistryUpdate.argtypes = [c_void_p, CALLBACK_TYPE]
        lib.DistConf_OnRegistryUpdate.restype = None
        
        lib.DistConf_GetAddress.argtypes = [c_void_p, c_char_p]
        lib.DistConf_GetAddress.restype = c_char_p
        
        lib.DistConf_GetGRPCAddress.argtypes = [c_void_p, c_char_p]
        lib.DistConf_GetGRPCAddress.restype = c_char_p
        
        lib.DistConf_GetCapability.argtypes = [c_void_p, c_char_p]
        lib.DistConf_GetCapability.restype = c_char_p
        
        lib.DistConf_GetFullConfig.argtypes = [c_void_p]
        lib.DistConf_GetFullConfig.restype = c_char_p
        
        lib.DistConf_Decrypt.argtypes = [c_void_p, c_char_p]
        lib.DistConf_Decrypt.restype = c_char_p

        lib.DistConf_ShareConfig.argtypes = [c_void_p, c_char_p]
        lib.DistConf_ShareConfig.restype = ctypes.c_bool
        
        lib.DistConf_FreeString.argtypes = [c_char_p]
        lib.DistConf_FreeString.restype = None
        
        return lib
    except Exception as e:
        print(f"Failed to load libdistconf: {e}")
        return None

# Singleton instance
lib = load_libdistconf()
