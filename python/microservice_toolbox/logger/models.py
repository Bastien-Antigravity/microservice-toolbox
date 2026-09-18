#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
LogLevel constants matching the canonical Go universal-logger levels.

DATA FLOW:
1. Input: Log severity strings or integer levels from callers.
2. Logic: Enforces exact numeric parity with universal-logger Go CGO constants.
3. Output: Typed integer log level for FFI dispatch.

KEY PARAMETERS:
- None (Enumeration Definitions).
"""

from enum import IntEnum


class LogLevel(IntEnum):
    """
    LogLevel constants matching the Go logger_models.Level.
    """
    DEBUG = 1
    STREAM = 2
    INFO = 3
    LOGON = 4
    LOGOUT = 5
    TRADE = 6
    SCHEDULE = 7
    REPORT = 8
    WARNING = 9
    ERROR = 10
    CRITICAL = 11

    @classmethod
    def from_str(cls, s: str) -> 'LogLevel':
        return getattr(cls, s.upper(), cls.INFO)
