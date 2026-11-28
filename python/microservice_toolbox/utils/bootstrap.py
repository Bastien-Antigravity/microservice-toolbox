#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Bootstrapping utilities for running Python processes in the Bastien-Antigravity ecosystem.
Manages automatic virtualenv re-execution, library path injections, and directory redirection.

DATA FLOW:
1. Input: Script execution directory and operating system environment variables.
2. Logic: Traverses directory tree to resolve obsidian-brain vault root and nearest .venv.
3. Output: Aligned sys.path, prepended PATH entries, and validated Python interpreter paths.

KEY PARAMETERS:
- start_dir: Base directory path to begin walking up toward the vault root.
"""

from os import (
    chdir as osChdir,
    environ as osEnviron,
    execl as osExecl,
    name as osName,
    pathsep as osPathsep,
)
from os.path import exists as osPathExists, samefile as osPathSamefile
from pathlib import Path as pathPath
from sys import (
    argv as sysArgv,
    executable as sysExecutable,
    path as sysPath,
    platform as sysPlatform,
    prefix as sysPrefix,
)

from microservice_toolbox.utils.lib_loader import resolve_library_path

# -----------------------------------------------------------------------------------------------

WORKSPACE_PYTHON_SDK_RELPATHS = (
    "microservice-toolbox/python",
    "universal-logger/unilog/python",
    "distributed-config/distconf/python",
    "safe-socket/safesock/python",
    "notif-server/notif/python",
)

# -----------------------------------------------------------------------------------------------


def sync_workspace_python_paths(workspace_root: pathPath, venv_dir: pathPath = None) -> list:
    """Synchronize local-first workspace Python SDK paths onto sys.path and venv .pth hooks.

    1. Locates .venv/lib/python*/site-packages (if venv_dir exists) and ensures it is on sys.path.
    2. Writes/updates _bastien_workspace.pth in site-packages with a safe 1-line startup hook.
    3. Prepends any candidate workspace SDK directories that exist on disk to sys.path index 0
       so local workspace source code always takes priority over site-packages while falling
       back automatically to site-packages when a local SDK directory does not exist.
    """
    ws_root = pathPath(workspace_root).resolve()
    candidate_paths = []
    seen_paths = set()

    def _add_candidate(path: pathPath) -> None:
        resolved = path.resolve()
        key = str(resolved)
        if key not in seen_paths:
            seen_paths.add(key)
            candidate_paths.append(resolved)

    for relpath in WORKSPACE_PYTHON_SDK_RELPATHS:
        _add_candidate(ws_root / relpath)

    if ws_root.is_dir():
        try:
            repo_dirs = sorted(
                (d for d in ws_root.iterdir() if d.is_dir() and not d.name.startswith(".")),
                key=lambda p: p.name,
            )
        except OSError:
            repo_dirs = []
        for repo_dir in repo_dirs:
            direct_py = repo_dir / "python"
            if (direct_py / "pyproject.toml").is_file() or (direct_py / "setup.py").is_file():
                _add_candidate(direct_py)
            try:
                sub_dirs = sorted(
                    (d for d in repo_dir.iterdir() if d.is_dir() and not d.name.startswith(".")),
                    key=lambda p: p.name,
                )
            except OSError:
                sub_dirs = []
            for sub_dir in sub_dirs:
                nested_py = sub_dir / "python"
                if (nested_py / "pyproject.toml").is_file() or (nested_py / "setup.py").is_file():
                    _add_candidate(nested_py)

    candidate_strs = [str(p) for p in candidate_paths]

    if venv_dir is not None:
        venv_path = pathPath(venv_dir)
        site_packages_dir = None
        venv_lib_dir = venv_path / "lib"
        if venv_lib_dir.exists():
            for py_dir in sorted(venv_lib_dir.glob("python*")):
                sp = py_dir / "site-packages"
                if sp.exists() and sp.is_dir():
                    site_packages_dir = sp
                    break
        if site_packages_dir is None:
            win_sp = venv_path / "Lib" / "site-packages"
            if win_sp.exists() and win_sp.is_dir():
                site_packages_dir = win_sp

        if site_packages_dir is not None:
            site_pkg_str = str(site_packages_dir.resolve())
            if site_pkg_str not in sysPath:
                sysPath.insert(0, site_pkg_str)

            pth_file = site_packages_dir / "_bastien_workspace.pth"
            pth_line = (
                f"import os, sys; [sys.path.insert(0, p) for p in {repr(candidate_strs)} "
                f"if os.path.isdir(p) and p not in sys.path]\n"
            )
            try:
                if not pth_file.exists() or pth_file.read_text(encoding="utf-8") != pth_line:
                    pth_file.write_text(pth_line, encoding="utf-8")
            except OSError:
                pass

    active_paths = []
    for path in reversed(candidate_paths):
        if path.is_dir():
            path_str = str(path)
            while path_str in sysPath:
                sysPath.remove(path_str)
            sysPath.insert(0, path_str)
            active_paths.insert(0, path_str)

    return active_paths


# -----------------------------------------------------------------------------------------------


def find_vault_root(start_dir: str) -> pathPath:
    """Walk up from the start directory until the vault root (obsidian-brain) is found.
    Identifies the vault by the presence of '08-Squad-Agent' or '00-AI-Orchestration' subdirectories."""
    current = pathPath(start_dir).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "08-Squad-Agent").is_dir() and (parent / "00-AI-Orchestration").is_dir():
            return parent
    # Fallback: walk up until a .venv is found (legacy behavior)
    current = pathPath(start_dir).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".venv").exists():
            return parent
    return current


# -----------------------------------------------------------------------------------------------


def _find_nearest_venv(start_dir: str) -> pathPath:
    """Walk up from the start directory until a directory containing .venv is found."""
    current = pathPath(start_dir).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".venv").exists():
            return parent
    return pathPath(start_dir).resolve()


# -----------------------------------------------------------------------------------------------


def get_venv_python(vault_root: pathPath) -> str:
    """Return the expected virtualenv python executable path for the current OS."""
    if osName == "nt":
        return str(vault_root / ".venv" / "Scripts" / "python.exe")
    return str(vault_root / ".venv" / "bin" / "python3")


# -----------------------------------------------------------------------------------------------


def ensure_virtualenv(start_dir: str) -> pathPath:
    """Re-launch the current script using the nearest virtualenv Python if available.
    Returns the vault root (obsidian-brain), not necessarily the .venv parent."""
    venv_dir = _find_nearest_venv(start_dir)
    venv_python = get_venv_python(venv_dir)
    if osPathExists(venv_python):
        try:
            if not osPathSamefile(sysExecutable, venv_python):
                # Prevent parent process environment (like PYTHONPATH) from polluting virtualenv isolation
                osEnviron.pop("PYTHONPATH", None)
                osExecl(venv_python, venv_python, *sysArgv)
        except OSError:
            pass
    return find_vault_root(start_dir)


# -----------------------------------------------------------------------------------------------


def prepend_venv_bin(vault_root: pathPath) -> None:
    """Ensure the vault virtualenv bin/Scripts directory is on PATH."""
    if osName == "nt":
        venv_bin = vault_root / ".venv" / "Scripts"
    else:
        venv_bin = vault_root / ".venv" / "bin"
    if venv_bin.exists():
        osEnviron["PATH"] = str(venv_bin) + osPathsep + osEnviron.get("PATH", "")


# -----------------------------------------------------------------------------------------------


def ensure_import_paths(script_dir: pathPath, vault_root: pathPath) -> None:
    """Ensure the script directory and vault root are available on sys.path."""
    for path in (script_dir, vault_root):
        path_str = str(path)
        if path_str not in sysPath:
            sysPath.append(path_str)


# -----------------------------------------------------------------------------------------------


def redirect_working_directory(target_dir: pathPath) -> pathPath:
    """Redirects the current working directory to the target directory reliably."""
    target = pathPath(target_dir).resolve()
    if target.exists() and target.is_dir():
        osChdir(target)
    return target


# -----------------------------------------------------------------------------------------------


def bootstrap_microservice(file_path: str, app_name: str = "app") -> None:
    """
    Hardened bootstrapper for Python microservices.
    1. Finds the repository root containing the local virtualenv, yaml config, or go.mod.
    2. Normalizes the current working directory to the repo root.
    3. Resolves and aligns the dynamic library (libunilog) to prevent double initialization crashes on macOS.
    4. Checks if running under the root's local virtualenv; if not, force relaunches via os.execl.
    5. Synchronizes virtualenv site-packages, _bastien_workspace.pth, and local-first workspace SDK paths.
    """
    # Resolve sys.argv[0] to an absolute path before changing the directory
    if sysArgv and sysArgv[0]:
        sysArgv[0] = str(pathPath(sysArgv[0]).resolve())

    # Resolve the directory of the calling file
    script_dir = pathPath(file_path).resolve().parent

    # Find repo root (directory containing .venv, standalone.yaml, or go.mod)
    repo_root = script_dir
    for parent in [script_dir] + list(script_dir.parents):
        if (parent / ".venv").exists() or (parent / "standalone.yaml").exists() or (parent / "go.mod").exists() or (parent / ".git").exists():
            repo_root = parent
            break

    # Redirect working directory to repo root
    if repo_root.exists() and repo_root.is_dir():
        osChdir(repo_root)

    # Find workspace root (check BASTIEN_CORE_ROOT first for external L3/L4/L5 domain services,
    # otherwise walk up until we find universal-logger, microservice-toolbox, go.work, .cargo/config.toml, or *.code-workspace)
    core_root_env = osEnviron.get("BASTIEN_CORE_ROOT", "").strip()
    core_root = pathPath(core_root_env).expanduser().resolve() if core_root_env else None
    if core_root is not None and (core_root / "microservice-toolbox").is_dir():
        workspace_root = core_root
    else:
        workspace_root = repo_root.parent
        for parent in [repo_root] + list(repo_root.parents):
            if (
                (parent / "universal-logger").is_dir()
                or (parent / "microservice-toolbox").is_dir()
                or (parent / "go.work").is_file()
                or (parent / ".cargo" / "config.toml").is_file()
                or any(parent.glob("*.code-workspace"))
            ):
                workspace_root = parent
                break

    # 1. Align dynamic library paths using the single source of truth in utils.lib_loader
    osEnviron["GODEBUG"] = "cgocheck=0"

    # 1.1 Prevent multi-threaded fork crashes (gRPC pthread_atfork handlers on macOS/Linux)
    # Child subprocesses (execve) do not need gRPC thread pools, avoiding macOS SIGILL & Linux fork deadlocks.
    osEnviron["GRPC_ENABLE_FORK_SUPPORT"] = "0"
    if sysPlatform == "darwin":
        osEnviron["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

    unilog_path = resolve_library_path("libunilog", "LIBUNILOG_PATH")
    if unilog_path:
        osEnviron["LIBUNILOG_PATH"] = unilog_path
        if sysPlatform == "darwin":
            # On macOS, prevent double Go runtime initialization by sharing the consolidated library
            osEnviron["LIBDISTCONF_PATH"] = unilog_path

    if not osEnviron.get("LIBDISTCONF_PATH"):
        distconf_path = resolve_library_path("libdistconf", "LIBDISTCONF_PATH")
        if distconf_path:
            osEnviron["LIBDISTCONF_PATH"] = distconf_path

    # 2. Virtual Environment Redirect
    _venv_dir = repo_root / ".venv"
    _venv_python = _venv_dir / ("Scripts/python.exe" if osName == "nt" else "bin/python3")

    if _venv_python.exists() and sysPrefix != str(_venv_dir):
        osEnviron.pop("PYTHONPATH", None)
        osExecl(str(_venv_python), str(_venv_python), *sysArgv)

    # Prepend virtualenv bin to PATH
    if osName == "nt":
        venv_bin = _venv_dir / "Scripts"
    else:
        venv_bin = _venv_dir / "bin"
    if venv_bin.exists():
        osEnviron["PATH"] = str(venv_bin) + osPathsep + osEnviron.get("PATH", "")

    # 3. Synchronize virtualenv site-packages, .pth workspace hook, and local-first SDK priority
    sync_workspace_python_paths(workspace_root, venv_dir=_venv_dir)
    if core_root is not None and core_root.resolve() != workspace_root.resolve():
        sync_workspace_python_paths(core_root, venv_dir=None)

    for repo_path in (repo_root, repo_root / "src"):
        if repo_path.is_dir():
            path_str = str(repo_path.resolve())
            while path_str in sysPath:
                sysPath.remove(path_str)
            sysPath.insert(0, path_str)




