#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Logger Protocol, native Python logger wrapper, and safe logging initialization helper.
"""

from typing import Protocol, runtime_checkable, Optional


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


class PythonLogger:
    """A pure-Python Logger wrapping standard logging. Used as a placeholder or standard backend without Go CGO requirements."""
    def __init__(self, name: str = "python-app"):
        import logging
        self._log = logging.getLogger(name)
        
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
    def add_metadata(self, key: str, value: str) -> None: pass


def ensure_safe_logger(logger: Optional[Logger]) -> Logger:
    """
    Strictly validates the logger. If None, returns a PythonLogger wrapping standard logging.
    """
    if logger is None:
        return PythonLogger()
    return logger
