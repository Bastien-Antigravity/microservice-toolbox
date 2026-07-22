#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Bootstrapping utilities for running Python processes in the Bastien-Antigravity ecosystem.
Manages automatic virtualenv re-execution, library path injections, and directory redirection.
"""

import os
import sys
from pathlib import Path


def find_vault_root(start_dir: str) -> Path:
    """Walk up from the start directory until the vault root (obsidian-brain) is found.
    Identifies the vault by the presence of '08-Base-Scripts' or '00-AI-Orchestration' subdirectories."""
    current = Path(start_dir).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "08-Base-Scripts").is_dir() and (parent / "00-AI-Orchestration").is_dir():
            return parent
    # Fallback: walk up until a .venv is found (legacy behavior)
    current = Path(start_dir).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".venv").exists():
            return parent
    return current


def _find_nearest_venv(start_dir: str) -> Path:
    """Walk up from the start directory until a directory containing .venv is found."""
    current = Path(start_dir).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".venv").exists():
            return parent
    return Path(start_dir).resolve()


def get_venv_python(vault_root: Path) -> str:
    """Return the expected virtualenv python executable path for the current OS."""
    if os.name == "nt":
        return str(vault_root / ".venv" / "Scripts" / "python.exe")
    return str(vault_root / ".venv" / "bin" / "python3")


def ensure_virtualenv(start_dir: str) -> Path:
    """Re-launch the current script using the nearest virtualenv Python if available.
    Returns the vault root (obsidian-brain), not necessarily the .venv parent."""
    venv_dir = _find_nearest_venv(start_dir)
    venv_python = get_venv_python(venv_dir)
    if os.path.exists(venv_python):
        try:
            if not os.path.samefile(sys.executable, venv_python):
                # Prevent parent process environment (like PYTHONPATH) from polluting virtualenv isolation
                os.environ.pop("PYTHONPATH", None)
                os.execl(venv_python, venv_python, *sys.argv)
        except OSError:
            pass
    return find_vault_root(start_dir)


def prepend_venv_bin(vault_root: Path) -> None:
    """Ensure the vault virtualenv bin/Scripts directory is on PATH."""
    if os.name == "nt":
        venv_bin = vault_root / ".venv" / "Scripts"
    else:
        venv_bin = vault_root / ".venv" / "bin"
    if venv_bin.exists():
        os.environ["PATH"] = str(venv_bin) + os.pathsep + os.environ.get("PATH", "")


def ensure_import_paths(script_dir: Path, vault_root: Path) -> None:
    """Ensure the script directory and vault root are available on sys.path."""
    for path in (script_dir, vault_root):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.append(path_str)


def redirect_working_directory(target_dir: Path) -> Path:
    """Redirects the current working directory to the target directory reliably."""
    target = Path(target_dir).resolve()
    if target.exists() and target.is_dir():
        os.chdir(target)
    return target


def bootstrap_microservice(file_path: str, app_name: str = "app") -> None:
    """
    Hardened bootstrapper for Python microservices.
    1. Finds the repository root containing the local virtualenv, yaml config, or go.mod.
    2. Normalizes the current working directory to the repo root.
    3. Resolves and aligns the dynamic library (libunilog) to prevent double initialization crashes on macOS.
    4. Checks if running under the root's local virtualenv; if not, force relaunches via os.execl.
    5. Appends virtualenv site-packages and standard 'src/' folder to sys.path.
    """
    import os
    import sys
    from pathlib import Path

    # Resolve sys.argv[0] to an absolute path before changing the directory
    if sys.argv and sys.argv[0]:
        sys.argv[0] = str(Path(sys.argv[0]).resolve())

    # Resolve the directory of the calling file
    script_dir = Path(file_path).resolve().parent

    # Find repo root (directory containing .venv, standalone.yaml, or go.mod)
    repo_root = script_dir
    for parent in [script_dir] + list(script_dir.parents):
        if (parent / ".venv").exists() or (parent / "standalone.yaml").exists() or (parent / "go.mod").exists() or (parent / ".git").exists():
            repo_root = parent
            break

    # Redirect working directory to repo root
    if repo_root.exists() and repo_root.is_dir():
        os.chdir(repo_root)

    # Find workspace root (walk up until we find a parent containing universal-logger, microservice-toolbox, or code-workspace)
    workspace_root = repo_root.parent
    for parent in [repo_root] + list(repo_root.parents):
        if (parent / "universal-logger").is_dir() or (parent / "microservice-toolbox").is_dir() or (parent / "Bastien-Antigravity-base.code-workspace").exists():
            workspace_root = parent
            break

    # 1. Align dynamic library path to prevent double Go runtime initialization
    os.environ["GODEBUG"] = "cgocheck=0"
    _dylib_path = None
    _ext = ".dylib" if sys.platform == "darwin" else (".dll" if sys.platform == "win32" else ".so")
    
    # Locate virtualenv lib site-packages dynamically
    _venv_lib_dir = repo_root / ".venv" / "lib"
    _venv_sp = None
    if _venv_lib_dir.exists():
        for _py_dir in _venv_lib_dir.glob("python*"):
            _sp = _py_dir / "site-packages"
            if _sp.exists():
                _venv_sp = _sp
                break

    _candidates = [
        workspace_root / "universal-logger" / "unilog" / "libunilog" / f"libunilog{_ext}",
        workspace_root / "universal-logger" / "unilog" / "python" / "unilog" / f"libunilog{_ext}"
    ]
    if _venv_sp:
        _candidates.insert(0, _venv_sp / "unilog" / f"libunilog{_ext}")

    for _c in _candidates:
        if _c.exists():
            _dylib_path = str(_c.resolve())
            break

    if _dylib_path:
        os.environ["LIBUNILOG_PATH"] = _dylib_path
        os.environ["LIBDISTCONF_PATH"] = _dylib_path

    # 2. Virtual Environment Redirect
    _venv_dir = repo_root / ".venv"
    _venv_python = _venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")

    if _venv_python.exists() and sys.prefix != str(_venv_dir):
        os.environ.pop("PYTHONPATH", None)
        os.execl(str(_venv_python), str(_venv_python), *sys.argv)

    # Prepend virtualenv bin to PATH
    if os.name == "nt":
        venv_bin = _venv_dir / "Scripts"
    else:
        venv_bin = _venv_dir / "bin"
    if venv_bin.exists():
        os.environ["PATH"] = str(venv_bin) + os.pathsep + os.environ.get("PATH", "")

    # Inject standard import paths
    for path in (repo_root, repo_root / "src", workspace_root / "microservice-toolbox" / "python"):
        path_str = str(path.resolve())
        if path.exists() and path_str not in sys.path:
            sys.path.insert(0, path_str)

    if _venv_sp:
        site_pkg_str = str(_venv_sp.resolve())
        if site_pkg_str not in sys.path:
            sys.path.insert(0, site_pkg_str)


