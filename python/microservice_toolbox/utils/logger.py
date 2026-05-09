#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides a standardized logging interface and fallback providers for the microservice fleet.
Ensures that all components have access to structured logging, whether running
standalone or integrated with the universal-logger.

DATA FLOW:
1. Components receive a logger via dependency injection.
2. If None, ensure_safe_logger provides a DefaultLogger.
3. Logger calls are routed to either terminal output or the shared logging engine.

KEY PARAMETERS:
- logger: An object implementing the Logger protocol.
"""

from typing import Any, Optional, Protocol, runtime_checkable

# -----------------------------------------------------------------------------------------------


@runtime_checkable
class Logger(Protocol):
    """
    Logger defines the standard interface for all logging operations in the ecosystem.
    Follows the 'I-prefix exclusion' architectural rule.
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


# -----------------------------------------------------------------------------------------------


class DefaultLogger:
    """Fallback logger that prints to terminal using existing logic."""

    Name = "DefaultLogger"

    # -----------------------------------------------------------------------------------------------

    def __init__(self):
        try:
            from .terminal_ui import print_internal_log

            self._print = print_internal_log
        except ImportError:
            self._print = self._simple_print

    # -----------------------------------------------------------------------------------------------

    def _simple_print(self, level: str, module: str, filename: str, line: str, message: str) -> None:
        print(f"[{level}] {message}")

    # -----------------------------------------------------------------------------------------------

    def debug(self, msg: str) -> None:
        self._print("DEBUG", self.Name, "logger.py", "24", msg)

    # -----------------------------------------------------------------------------------------------

    def info(self, msg: str) -> None:
        self._print("INFO", self.Name, "logger.py", "25", msg)

    # -----------------------------------------------------------------------------------------------

    def warning(self, msg: str) -> None:
        self._print("WARNING", self.Name, "logger.py", "26", msg)

    # -----------------------------------------------------------------------------------------------

    def error(self, msg: str) -> None:
        self._print("ERROR", self.Name, "logger.py", "27", msg)

    # -----------------------------------------------------------------------------------------------

    def critical(self, msg: str) -> None:
        self._print("CRITICAL", self.Name, "logger.py", "28", msg)

    # -----------------------------------------------------------------------------------------------

    def logon(self, msg: str) -> None:
        self._print("LOGON", self.Name, "logger.py", "29", msg)

    # -----------------------------------------------------------------------------------------------

    def logout(self, msg: str) -> None:
        self._print("LOGOUT", self.Name, "logger.py", "30", msg)

    # -----------------------------------------------------------------------------------------------

    def trade(self, msg: str) -> None:
        self._print("TRADE", self.Name, "logger.py", "31", msg)

    # -----------------------------------------------------------------------------------------------

    def schedule(self, msg: str) -> None:
        self._print("SCHEDULE", self.Name, "logger.py", "32", msg)

    # -----------------------------------------------------------------------------------------------

    def report(self, msg: str) -> None:
        self._print("REPORT", self.Name, "logger.py", "33", msg)

    # -----------------------------------------------------------------------------------------------

    def stream(self, msg: str) -> None:
        self._print("STREAM", self.Name, "logger.py", "34", msg)

    # -----------------------------------------------------------------------------------------------

    def add_metadata(self, key: str, value: str) -> None:
        print(f"[META] {key}={value}")


# -----------------------------------------------------------------------------------------------


class UniLogger:
    """Wrapper for the compiled universal-logger."""

    Name = "UniLogger"

    # -----------------------------------------------------------------------------------------------

    def __init__(self, unilog_instance: Any):
        self._inner = unilog_instance

    # -----------------------------------------------------------------------------------------------

    def debug(self, msg: str) -> None:
        self._inner.debug(msg)

    # -----------------------------------------------------------------------------------------------

    def info(self, msg: str) -> None:
        self._inner.info(msg)

    # -----------------------------------------------------------------------------------------------

    def warning(self, msg: str) -> None:
        self._inner.warning(msg)

    # -----------------------------------------------------------------------------------------------

    def error(self, msg: str) -> None:
        self._inner.error(msg)

    # -----------------------------------------------------------------------------------------------

    def critical(self, msg: str) -> None:
        self._inner.critical(msg)

    # -----------------------------------------------------------------------------------------------

    def logon(self, msg: str) -> None:
        if hasattr(self._inner, "logon"):
            self._inner.logon(msg)
        else:
            self.info(f"[LOGON] {msg}")

    # -----------------------------------------------------------------------------------------------

    def logout(self, msg: str) -> None:
        if hasattr(self._inner, "logout"):
            self._inner.logout(msg)
        else:
            self.info(f"[LOGOUT] {msg}")

    # -----------------------------------------------------------------------------------------------

    def trade(self, msg: str) -> None:
        if hasattr(self._inner, "trade"):
            self._inner.trade(msg)
        else:
            self.info(f"[TRADE] {msg}")

    # -----------------------------------------------------------------------------------------------

    def schedule(self, msg: str) -> None:
        if hasattr(self._inner, "schedule"):
            self._inner.schedule(msg)
        else:
            self.info(f"[SCHEDULE] {msg}")

    # -----------------------------------------------------------------------------------------------

    def report(self, msg: str) -> None:
        if hasattr(self._inner, "report"):
            self._inner.report(msg)
        else:
            self.info(f"[REPORT] {msg}")

    # -----------------------------------------------------------------------------------------------

    def stream(self, msg: str) -> None:
        if hasattr(self._inner, "stream"):
            self._inner.stream(msg)
        else:
            self.info(f"[STREAM] {msg}")

    # -----------------------------------------------------------------------------------------------

    def add_metadata(self, key: str, value: str) -> None:
        if hasattr(self._inner, "add_metadata"):
            self._inner.add_metadata(key, value)
        elif hasattr(self._inner, "add_tag"):
            self._inner.add_tag(key, value)


# -----------------------------------------------------------------------------------------------


def ensure_safe_logger(logger: Optional[Logger]) -> Logger:
    """Ensures a valid logger is returned, falling back to DefaultLogger if None."""
    if logger is None:
        return DefaultLogger()
    return logger
