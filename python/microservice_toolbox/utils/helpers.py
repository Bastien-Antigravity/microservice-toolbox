#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides shared utility functions and helper methods used across the toolbox.

DATA FLOW:
1. Retrieval of system-level metadata (e.g., hostname).
2. Result caching to prevent redundant system calls.

KEY PARAMETERS:
None
"""

from functools import lru_cache as functoolsLruCache
from os import getcwd as osGetcwd
from os.path import abspath as osPathAbspath, dirname as osPathDirname, isfile as osPathIsfile
from socket import gethostname as socketGetHostName
from sys import argv as sysArgv

# -----------------------------------------------------------------------------------------------


@functoolsLruCache(maxsize=1)
def get_hostname() -> str:
    """Get system hostname (cached)"""
    try:
        return socketGetHostName()
    except Exception:
        return "localhost"


# -----------------------------------------------------------------------------------------------


def get_base_dir() -> str:
    """
    Returns the absolute path to the directory containing the main script.
    Provides a stable anchor for logs and config files, similar to the Go implementation.
    """
    try:
        # Try sysArgv[0] first (standard script execution)
        main_path = osPathAbspath(sysArgv[0])
        if osPathIsfile(main_path):
            return osPathDirname(main_path)
        return osGetcwd()
    except Exception:
        return osGetcwd()
