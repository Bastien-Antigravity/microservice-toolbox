#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Dynamic semantic version resolution for Python microservices and tools.
Adheres to VERSION.txt as the ecosystem Single Source of Truth.

DATA FLOW:
Env (APP_VERSION) -> Caller/CWD Directory Climber (VERSION.txt) -> Default Fallback (0.0.1)

KEY PARAMETERS:
- get_version(): Resolves and caches the semantic version string.
"""

from .version import DEFAULT_FALLBACK_VERSION, get_version, reset_version, resolve_version, set_version

__all__ = [
    "get_version",
    "resolve_version",
    "set_version",
    "reset_version",
    "DEFAULT_FALLBACK_VERSION",
]
