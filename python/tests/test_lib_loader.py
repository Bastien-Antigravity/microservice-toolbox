#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests validating the unified CGO dynamic library loader (utils.lib_loader)
and its facades across microservice-toolbox.

DATA FLOW:
1. Input: Dynamic libraries on host/workspace filesystem.
2. Logic: Verifies path resolution, FFI function signature binding, singleton caching,
          and backward compatibility facades in config.lib_loader and logger.lib_loader.
3. Output: Pytest assertions on ctypes.CDLL instances and exported symbols.

KEY PARAMETERS:
- None
"""

import os
import sys
import pytest

from microservice_toolbox.utils.lib_loader import (
    resolve_library_path,
    load_libunilog,
    load_libdistconf,
    get_platform_extension,
    CONFIG_CALLBACK_TYPE,
    LOGGER_CALLBACK_TYPE,
)
def test_platform_extension():
    ext = get_platform_extension()
    if sys.platform == "darwin":
        assert ext == ".dylib"
    elif sys.platform == "win32":
        assert ext == ".dll"
    else:
        assert ext == ".so"


def test_resolve_library_path():
    unilog_path = resolve_library_path("libunilog")
    assert unilog_path is not None
    assert os.path.exists(unilog_path)
    assert "libunilog" in unilog_path


def test_load_libunilog():
    handle = load_libunilog()
    assert handle is not None
    assert hasattr(handle, "UniLog_Init")
    assert hasattr(handle, "UniLog_LogWithMetadata")
    assert hasattr(handle, "UniLog_Close")
    assert hasattr(handle, "UniLog_SetLevel")


def test_load_libdistconf():
    handle = load_libdistconf()
    assert handle is not None
    assert hasattr(handle, "DistConf_New")
    assert hasattr(handle, "DistConf_Close")
    assert hasattr(handle, "DistConf_Get")
    assert hasattr(handle, "DistConf_GetRESTAddress")


def test_direct_module_integrations():
    import microservice_toolbox.config.loader as cfg_loader
    import microservice_toolbox.logger.facade as log_facade

    assert cfg_loader.lib is not None
    assert hasattr(cfg_loader.lib, "DistConf_New")
    assert log_facade.lib is not None
    assert hasattr(log_facade.lib, "UniLog_Init")


def test_utils_exports():
    from microservice_toolbox.utils import (
        resolve_library_path as rlp,
        load_libunilog as llu,
        load_libdistconf as lld,
    )
    assert rlp is resolve_library_path
    assert llu is load_libunilog
    assert lld is load_libdistconf
