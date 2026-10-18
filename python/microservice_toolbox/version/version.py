#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Implements hierarchical dynamic semver resolution for Python components.
Guarantees VERSION.txt is treated as the Single Source of Truth.

DATA FLOW:
1. Environment variable override (APP_VERSION / SERVICE_VERSION).
2. Explicit caller directory climbing upwards for VERSION.txt.
3. Fallback to 0.0.1.

KEY PARAMETERS:
- caller_file: Optional path from caller to start upward directory climb.
- fallback: Default version string if resolution fails.
"""

from inspect import stack as inspectStack
from os import environ as osEnviron
from pathlib import Path
from threading import Lock
from typing import Optional

DEFAULT_FALLBACK_VERSION = "0.0.1"

_cached_version: Optional[str] = None
_lock = Lock()

# -----------------------------------------------------------------------------------------------


def get_version(caller_file: Optional[str] = None, fallback: str = DEFAULT_FALLBACK_VERSION) -> str:
    """
    Returns the dynamic semantic version of the microservice.
    Caches the result after first resolution.
    """
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    with _lock:
        if _cached_version is not None:
            return _cached_version

        v = resolve_version(caller_file=caller_file, fallback=fallback)
        _cached_version = v
        return _cached_version


# -----------------------------------------------------------------------------------------------


def resolve_version(caller_file: Optional[str] = None, fallback: str = DEFAULT_FALLBACK_VERSION) -> str:
    """
    Performs full hierarchical version resolution without caching.
    """
    # 1. Environment variables
    for env_var in ("APP_VERSION", "SERVICE_VERSION"):
        val = osEnviron.get(env_var, "").strip()
        if val:
            return val

    # 2. Determine start search directories
    start_dirs = []

    if caller_file:
        try:
            start_dirs.append(Path(caller_file).resolve().parent)
        except Exception:
            pass

    if not start_dirs:
        try:
            stk = inspectStack()
            for frame_info in stk[1:]:
                fn = frame_info.filename
                if fn and not fn.endswith("version.py") and "threading.py" not in fn and "importlib" not in fn:
                    start_dirs.append(Path(fn).resolve().parent)
                    break
        except Exception:
            pass

    try:
        start_dirs.append(Path.cwd().resolve())
    except Exception:
        pass

    # 3. Climb directory tree looking for VERSION.txt
    for start_dir in start_dirs:
        curr = start_dir
        for _ in range(12):
            version_file = curr / "VERSION.txt"
            if version_file.is_file():
                try:
                    content = version_file.read_text(encoding="utf-8").strip()
                    if content:
                        return content
                except OSError:
                    pass

            if (curr / ".git").exists() or curr.parent == curr:
                break
            curr = curr.parent

    # 4. Fallback
    return fallback


# -----------------------------------------------------------------------------------------------


def set_version(v: str) -> None:
    """Explicitly sets the cached version (primarily for testing)."""
    global _cached_version
    with _lock:
        _cached_version = v.strip() or DEFAULT_FALLBACK_VERSION


# -----------------------------------------------------------------------------------------------


def reset_version() -> None:
    """Clears the cached version so the next get_version() will re-resolve."""
    global _cached_version
    with _lock:
        _cached_version = None
