#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Formats and prints internal toolbox log messages to the terminal.
Ensures consistent visual output with Go/Rust implementations.

DATA FLOW:
1. Receives log metadata (level, module, filename, line, message).
2. Generates precision timestamp and retrieves hostname.
3. Colorizes output and prints in fixed-column format.

KEY PARAMETERS:
- level: Logging level (DEBUG, INFO, etc.).
- message: The log content.
"""

from datetime import datetime as datetimeDateTime
from typing import Any

from .helpers import get_hostname

#-----------------------------------------------------------------------------------------------

def print_internal_log(level: str, module: str, filename: str, line: str, message: str) -> None:
    """Formats and prints an internal toolbox log message"""
    # Precision timestamp in ISO 8601 format
    timestamp = datetimeDateTime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "000Z"
    hostname = get_hostname()

    # Colorize level
    colors = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "LOGON": "\033[32m",
        "LOGOUT": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[31m",
    }
    color = colors.get(level, "")
    colored_level = f"{color}{truncate(level, 10):<10}\033[0m"

    # Fixed column format: 33-12-15-10-20-25-6 message
    print(
        f"{timestamp:<33} "
        f"{truncate(hostname, 12):<12} "
        f"{truncate('microservice-toolbox', 15):<15} "
        f"{colored_level} "
        f"{truncate(filename, 20):<20} "
        f"{truncate(module, 25):<25} "
        f"{truncate(line, 6):<6} "
        f"{message}"
    )

#-----------------------------------------------------------------------------------------------

def truncate(s: str, max_len: int) -> str:
    """Helper to truncate strings to a maximum length."""
    return s[:max_len] if len(s) > max_len else s
