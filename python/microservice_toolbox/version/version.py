#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Implements hierarchical dynamic semver resolution for Python components.
Guarantees VERSION.txt is the Single Source of Truth with fail-fast errors.

DATA FLOW:
1. Caller/CWD directory climbing upwards for VERSION.txt (bounded by .git / 12 levels).
2. Fail-fast RuntimeError when VERSION.txt is missing or empty.

KEY PARAMETERS:
- caller_file: Optional path from caller to start upward directory climb.
"""

from inspect import stack as inspectStack
from pathlib import Path as pathPath
from threading import Lock as thLock
from typing import Optional as typeOptional

_THIS_FILE = str(pathPath(__file__).resolve())
_cached_version: typeOptional[str] = None
_lock = thLock()

# -----------------------------------------------------------------------------------------------


def get_version(caller_file: typeOptional[str] = None) -> str:
    """
    Returns the dynamic semantic version resolved strictly from VERSION.txt.
    Caches the result after first resolution and raises RuntimeError if missing.
    """
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    with _lock:
        if _cached_version is not None:
            return _cached_version

        v = resolve_version(caller_file=caller_file)
        _cached_version = v
        return _cached_version


# -----------------------------------------------------------------------------------------------


def resolve_version(caller_file: typeOptional[str] = None) -> str:
    """
    Resolves semantic version strictly from VERSION.txt without caching.
    Raises RuntimeError if no non-empty VERSION.txt is found.
    """
    # 1. Determine start search directories
    start_dirs = []

    if caller_file:
        start_dirs.append(pathPath(caller_file).resolve().parent)
    else:
        stk = inspectStack()
        for frame_info in stk[1:]:
            fn = frame_info.filename
            if not fn or fn.startswith("<"):
                continue
            resolved_fn = str(pathPath(fn).resolve())
            if resolved_fn != _THIS_FILE and "threading.py" not in fn and "importlib" not in fn:
                start_dirs.append(pathPath(resolved_fn).parent)
                break

    start_dirs.append(pathPath.cwd().resolve())

    # 2. Climb directory tree looking for VERSION.txt
    for start_dir in start_dirs:
        curr = start_dir
        for _ in range(12):
            version_file = curr / "VERSION.txt"
            if version_file.is_file():
                content = version_file.read_text(encoding="utf-8").strip()
                if content:
                    return content

            if (curr / ".git").exists() or curr.parent == curr:
                break
            curr = curr.parent

    # 3. Fail-fast
    raise RuntimeError("version.resolve_version: VERSION.txt not found or empty (FAIL-FAST)")


# -----------------------------------------------------------------------------------------------


def set_version(v: str) -> None:
    """Explicitly sets the cached version (primarily for testing). Rejects empty values."""
    global _cached_version
    trimmed = (v or "").strip()
    if not trimmed:
        raise ValueError("version.set_version: version string must not be empty (FAIL-FAST)")
    with _lock:
        _cached_version = trimmed


# -----------------------------------------------------------------------------------------------


def reset_version() -> None:
    """Clears the cached version so the next get_version() will re-resolve."""
    global _cached_version
    with _lock:
        _cached_version = None
