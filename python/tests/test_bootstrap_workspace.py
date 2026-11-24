#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests validating local-first Python workspace SDK resolution in utils.bootstrap.

DATA FLOW:
1. Input: Mock workspace_root and .venv/lib/python*/site-packages directory trees.
2. Logic: Exercises sync_workspace_python_paths with present and absent local SDK directories,
          lower-priority sys.path entries, and read-only site-packages directories.
3. Output: Pytest assertions on sys.path precedence, _bastien_workspace.pth contents, and fallback.

KEY PARAMETERS:
- None
"""

from pathlib import Path
from sys import path as sysPath

from microservice_toolbox.utils.bootstrap import (
    WORKSPACE_PYTHON_SDK_RELPATHS,
    sync_workspace_python_paths,
)

# -----------------------------------------------------------------------------------------------


def test_sync_workspace_python_paths_prefers_local_over_site_packages(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspace"
    local_toolbox = ws_root / "microservice-toolbox" / "python"
    local_unilog = ws_root / "universal-logger" / "unilog" / "python"
    local_toolbox.mkdir(parents=True, exist_ok=True)
    local_unilog.mkdir(parents=True, exist_ok=True)

    venv_dir = tmp_path / "service" / ".venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    mock_sys_path = list(sysPath)
    monkeypatch.setattr("microservice_toolbox.utils.bootstrap.sysPath", mock_sys_path)

    active = sync_workspace_python_paths(ws_root, venv_dir=venv_dir)

    toolbox_str = str(local_toolbox.resolve())
    unilog_str = str(local_unilog.resolve())
    site_pkg_str = str(site_packages.resolve())
    absent_distconf_str = str((ws_root / "distributed-config" / "distconf" / "python").resolve())

    assert active == [toolbox_str, unilog_str]
    assert toolbox_str in mock_sys_path
    assert unilog_str in mock_sys_path
    assert site_pkg_str in mock_sys_path
    assert absent_distconf_str not in mock_sys_path

    assert mock_sys_path.index(toolbox_str) < mock_sys_path.index(site_pkg_str)
    assert mock_sys_path.index(unilog_str) < mock_sys_path.index(site_pkg_str)

    pth_file = site_packages / "_bastien_workspace.pth"
    assert pth_file.is_file()
    pth_content = pth_file.read_text(encoding="utf-8")
    assert pth_content.startswith("import os, sys; [sys.path.insert(0, p) for p in [")
    assert "if os.path.isdir(p) and p not in sys.path]" in pth_content
    assert len(pth_content.strip().splitlines()) == 1
    for relpath in WORKSPACE_PYTHON_SDK_RELPATHS:
        assert str((ws_root / relpath).resolve()) in pth_content


# -----------------------------------------------------------------------------------------------


def test_sync_workspace_python_paths_promotes_existing_lower_priority_path(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspace"
    local_distconf = ws_root / "distributed-config" / "distconf" / "python"
    local_distconf.mkdir(parents=True, exist_ok=True)

    venv_dir = tmp_path / "service" / ".venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    distconf_str = str(local_distconf.resolve())
    site_pkg_str = str(site_packages.resolve())

    # Simulate site-packages initially outranking local workspace path
    mock_sys_path = [site_pkg_str, "/usr/lib/python3.12", distconf_str]
    monkeypatch.setattr("microservice_toolbox.utils.bootstrap.sysPath", mock_sys_path)

    active = sync_workspace_python_paths(ws_root, venv_dir=venv_dir)

    assert active == [distconf_str]
    assert mock_sys_path.count(distconf_str) == 1
    assert mock_sys_path.index(distconf_str) < mock_sys_path.index(site_pkg_str)


# -----------------------------------------------------------------------------------------------


def test_sync_workspace_python_paths_fallback_when_absent(tmp_path, monkeypatch):
    ws_root = tmp_path / "empty_workspace"
    ws_root.mkdir(parents=True, exist_ok=True)

    venv_dir = tmp_path / "service" / ".venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    mock_sys_path = ["/usr/lib/python3.12"]
    monkeypatch.setattr("microservice_toolbox.utils.bootstrap.sysPath", mock_sys_path)

    active = sync_workspace_python_paths(ws_root, venv_dir=venv_dir)

    site_pkg_str = str(site_packages.resolve())
    assert active == []
    assert site_pkg_str in mock_sys_path
    for relpath in WORKSPACE_PYTHON_SDK_RELPATHS:
        assert str((ws_root / relpath).resolve()) not in mock_sys_path

    pth_file = site_packages / "_bastien_workspace.pth"
    assert pth_file.is_file()


# -----------------------------------------------------------------------------------------------


def test_sync_workspace_python_paths_ignores_readonly_pth_error(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspace"
    local_safesock = ws_root / "safe-socket" / "safesock" / "python"
    local_safesock.mkdir(parents=True, exist_ok=True)

    venv_dir = tmp_path / "service" / ".venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    def _raise_oserror(self, *args, **kwargs):
        raise OSError("Read-only file system")

    monkeypatch.setattr(Path, "write_text", _raise_oserror)
    mock_sys_path = []
    monkeypatch.setattr("microservice_toolbox.utils.bootstrap.sysPath", mock_sys_path)

    active = sync_workspace_python_paths(ws_root, venv_dir=venv_dir)

    assert active == [str(local_safesock.resolve())]
    assert str(local_safesock.resolve()) in mock_sys_path
    assert str(site_packages.resolve()) in mock_sys_path


# -----------------------------------------------------------------------------------------------


def test_sync_workspace_python_paths_discovers_custom_new_ecosystem_toolbox(tmp_path, monkeypatch):
    ws_root = tmp_path / "my-custom-ecosystem"
    custom_toolbox = ws_root / "quantum-toolbox" / "python"
    custom_toolbox.mkdir(parents=True, exist_ok=True)
    (custom_toolbox / "pyproject.toml").write_text('[project]\nname = "quantum-toolbox"\n', encoding="utf-8")

    venv_dir = tmp_path / "custom-service" / ".venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    site_pkg_str = str(site_packages.resolve())
    custom_str = str(custom_toolbox.resolve())
    mock_sys_path = [site_pkg_str, "/usr/lib/python3.12"]
    monkeypatch.setattr("microservice_toolbox.utils.bootstrap.sysPath", mock_sys_path)

    active = sync_workspace_python_paths(ws_root, venv_dir=venv_dir)

    assert custom_str in active
    assert mock_sys_path[0] == custom_str
    assert mock_sys_path.index(custom_str) < mock_sys_path.index(site_pkg_str)

    pth_file = site_packages / "_bastien_workspace.pth"
    assert pth_file.is_file()
    pth_content = pth_file.read_text(encoding="utf-8")
    assert custom_str in pth_content
