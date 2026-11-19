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

from microservice_toolbox.utils.lib_loader import (
    get_platform_extension,
    load_libdistconf,
    load_libunilog,
    resolve_library_path,
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
        load_libdistconf as lld,
        load_libunilog as llu,
        resolve_library_path as rlp,
    )
    assert rlp is resolve_library_path
    assert llu is load_libunilog
    assert lld is load_libdistconf


def test_resolve_library_path_bastien_core_root(tmp_path, monkeypatch):
    ext = get_platform_extension()
    core_root = tmp_path / "core_ecosystem"

    unilog_bin = core_root / "universal-logger" / "bin" / f"libunilog{ext}"
    unilog_bin.parent.mkdir(parents=True, exist_ok=True)
    unilog_bin.write_bytes(b"stub-unilog")

    safesock_root = core_root / "safe-socket" / f"libsafesocket{ext}"
    safesock_root.parent.mkdir(parents=True, exist_ok=True)
    safesock_root.write_bytes(b"stub-safesocket")

    distconf_bin = core_root / "distributed-config" / "bin" / f"libdistconf{ext}"
    distconf_bin.parent.mkdir(parents=True, exist_ok=True)
    distconf_bin.write_bytes(b"stub-distconf")

    monkeypatch.setenv("BASTIEN_CORE_ROOT", str(core_root))
    monkeypatch.delenv("LIBUNILOG_PATH", raising=False)
    monkeypatch.delenv("LIBSAFESOCKET_PATH", raising=False)
    monkeypatch.delenv("LIBDISTCONF_PATH", raising=False)

    assert resolve_library_path("libunilog", "LIBUNILOG_PATH") == str(unilog_bin.resolve())
    assert resolve_library_path("libsafesocket", "LIBSAFESOCKET_PATH") == str(safesock_root.resolve())
    assert resolve_library_path("libdistconf", "LIBDISTCONF_PATH") == str(distconf_bin.resolve())

    # Priority 1 explicit override still takes precedence over BASTIEN_CORE_ROOT
    explicit = tmp_path / f"override_libunilog{ext}"
    explicit.write_bytes(b"override")
    monkeypatch.setenv("LIBUNILOG_PATH", str(explicit))
    assert resolve_library_path("libunilog", "LIBUNILOG_PATH") == str(explicit.resolve())


def test_bootstrap_microservice_bastien_core_root(tmp_path, monkeypatch):
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice

    ext = get_platform_extension()
    core_root = tmp_path / "core_ecosystem"
    core_py = core_root / "microservice-toolbox" / "python"
    core_py.mkdir(parents=True, exist_ok=True)
    unilog_bin = core_root / "universal-logger" / "bin" / f"libunilog{ext}"
    unilog_bin.parent.mkdir(parents=True, exist_ok=True)
    unilog_bin.write_bytes(b"stub-unilog")
    distconf_bin = core_root / "distributed-config" / "bin" / f"libdistconf{ext}"
    distconf_bin.parent.mkdir(parents=True, exist_ok=True)
    distconf_bin.write_bytes(b"stub-distconf")

    domain_service = tmp_path / "external_domain" / "my_service"
    domain_service.mkdir(parents=True, exist_ok=True)
    (domain_service / "standalone.yaml").write_text("common:\n  name: my_service\n", encoding="utf-8")
    entry_file = domain_service / "main.py"
    entry_file.write_text("# stub\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BASTIEN_CORE_ROOT", str(core_root))
    monkeypatch.delenv("LIBUNILOG_PATH", raising=False)
    monkeypatch.delenv("LIBDISTCONF_PATH", raising=False)
    monkeypatch.delenv("GODEBUG", raising=False)
    monkeypatch.delenv("GRPC_ENABLE_FORK_SUPPORT", raising=False)
    monkeypatch.delenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", raising=False)
    monkeypatch.setattr(sys, "argv", [str(entry_file)])

    orig_sys_path = list(sys.path)
    try:
        bootstrap_microservice(str(entry_file), app_name="my_service")
        assert str(core_py.resolve()) in sys.path
        assert os.environ.get("LIBUNILOG_PATH") == str(unilog_bin.resolve())
    finally:
        sys.path[:] = orig_sys_path
