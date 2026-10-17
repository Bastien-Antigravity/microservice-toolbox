#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Logger Protocol definition, native Python logger wrapper, and safe logger fallback helper.

DATA FLOW:
1. Input: Log severity strings, messages, and optional metadata from application callers.
2. Logic: Enforces ecosystem Logger protocol compliance across concrete implementations.
3. Output: Dispatched log messages or safe fallback logger instance.

KEY PARAMETERS:
- logger: Optional Logger instance passed to ensure_safe_logger.
"""

from logging import getLogger as loggingGetLogger
from os import environ as osEnviron
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class Logger(Protocol):
    """
    Logger defines the standard interface for all logging operations in the ecosystem.
    """
    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
    def critical(self, msg: str) -> None: ...
    def logon(self, msg: str) -> None: ...
    def logout(self, msg: str) -> None: ...
    def trade(self, msg: str) -> None: ...
    def schedule(self, msg: str) -> None: ...
    def report(self, msg: str) -> None: ...
    def stream(self, msg: str) -> None: ...
    def add_metadata(self, key: str, value: str) -> None: ...


class FallbackTestLogger:
    """
    An offline fallback logger wrapping Python standard logging for isolated unit tests.
    Used ONLY when the universal-logger Go CGO engine (libunilog) is unavailable in offline test environments.
    Strictly prohibited for production microservice execution.
    """
    def __init__(self, name: str = "python-app"):
        self._log = loggingGetLogger(name)
        self._metadata: dict[str, str] = {}

    def debug(self, msg: str) -> None: self._log.debug(msg)
    def info(self, msg: str) -> None: self._log.info(msg)
    def warning(self, msg: str) -> None: self._log.warning(msg)
    def error(self, msg: str) -> None: self._log.error(msg)
    def critical(self, msg: str) -> None: self._log.critical(msg)
    def logon(self, msg: str) -> None: self._log.info(f"[LOGON] {msg}")
    def logout(self, msg: str) -> None: self._log.info(f"[LOGOUT] {msg}")
    def trade(self, msg: str) -> None: self._log.info(f"[TRADE] {msg}")
    def schedule(self, msg: str) -> None: self._log.info(f"[SCHEDULE] {msg}")
    def report(self, msg: str) -> None: self._log.info(f"[REPORT] {msg}")
    def stream(self, msg: str) -> None: self._log.info(f"[STREAM] {msg}")
    def add_metadata(self, key: str, value: str) -> None: self._metadata[key] = value


# Retained as backwards-compatible alias for unit tests
PythonLogger = FallbackTestLogger


def ensure_safe_logger(logger: Optional[Logger]) -> Logger:
    """
    Strictly validates the logger. If None, returns a FallbackTestLogger for offline test environments.
    In strict mode (STRICT_LOGGER=true), raises RuntimeError to prevent microservices from running dark.
    """
    if logger is None:
        if osEnviron.get("STRICT_LOGGER") == "true":
            raise RuntimeError(
                "CRITICAL ARCHITECTURAL VIOLATION: Nil logger passed to ensure_safe_logger in strict mode. "
                "Microservices must inject a valid logger via bootstrap."
            )
        return FallbackTestLogger()
    return logger

