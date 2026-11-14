#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Dynamic semantic version resolution for Python microservices and tools.
Adheres to VERSION.txt as the ecosystem Single Source of Truth.

DATA FLOW:
Caller/CWD Directory Climber (VERSION.txt) -> Fail-Fast RuntimeError

KEY PARAMETERS:
- get_version(): Resolves and caches the semantic version string.
"""

from .version import get_version, reset_version, resolve_version, set_version

__all__ = [
    "get_version",
    "resolve_version",
    "set_version",
    "reset_version",
]
