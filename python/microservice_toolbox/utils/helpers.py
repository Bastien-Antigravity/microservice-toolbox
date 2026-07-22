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
from socket import gethostname as socketGetHostName

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
    import sys
    import os
    try:
        # Try sys.argv[0] first (standard script execution)
        main_path = os.path.abspath(sys.argv[0])
        if os.path.isfile(main_path):
            return os.path.dirname(main_path)
        return os.getcwd()
    except Exception:
        return os.getcwd()
