from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class ILogger(Protocol):
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


class DefaultLogger:
    """Fallback logger that prints to terminal using existing logic."""

    def __init__(self):
        try:
            from .terminal_ui import print_internal_log

            self._print = print_internal_log
        except ImportError:
            self._print = self._simple_print

    def _simple_print(self, level, module, filename, line, message):
        print(f"[{level}] {message}")

    def debug(self, msg: str):
        self._print("DEBUG", "DefaultLogger", "logger.py", "24", msg)

    def info(self, msg: str):
        self._print("INFO", "DefaultLogger", "logger.py", "25", msg)

    def warning(self, msg: str):
        self._print("WARNING", "DefaultLogger", "logger.py", "26", msg)

    def error(self, msg: str):
        self._print("ERROR", "DefaultLogger", "logger.py", "27", msg)

    def critical(self, msg: str):
        self._print("CRITICAL", "DefaultLogger", "logger.py", "28", msg)

    def logon(self, msg: str):
        self._print("LOGON", "DefaultLogger", "logger.py", "29", msg)

    def logout(self, msg: str):
        self._print("LOGOUT", "DefaultLogger", "logger.py", "30", msg)

    def trade(self, msg: str):
        self._print("TRADE", "DefaultLogger", "logger.py", "31", msg)

    def schedule(self, msg: str):
        self._print("SCHEDULE", "DefaultLogger", "logger.py", "32", msg)

    def report(self, msg: str):
        self._print("REPORT", "DefaultLogger", "logger.py", "33", msg)

    def stream(self, msg: str):
        self._print("STREAM", "DefaultLogger", "logger.py", "34", msg)

    def add_metadata(self, key: str, value: str):
        print(f"[META] {key}={value}")


class UniLogger:
    """Wrapper for the compiled universal-logger."""

    def __init__(self, unilog_instance: Any):
        self._inner = unilog_instance

    def debug(self, msg: str):
        self._inner.debug(msg)

    def info(self, msg: str):
        self._inner.info(msg)

    def warning(self, msg: str):
        self._inner.warning(msg)

    def error(self, msg: str):
        self._inner.error(msg)

    def critical(self, msg: str):
        self._inner.critical(msg)

    def logon(self, msg: str):
        if hasattr(self._inner, "logon"):
            self._inner.logon(msg)
        else:
            self.info(f"[LOGON] {msg}")

    def logout(self, msg: str):
        if hasattr(self._inner, "logout"):
            self._inner.logout(msg)
        else:
            self.info(f"[LOGOUT] {msg}")

    def trade(self, msg: str):
        if hasattr(self._inner, "trade"):
            self._inner.trade(msg)
        else:
            self.info(f"[TRADE] {msg}")

    def schedule(self, msg: str):
        if hasattr(self._inner, "schedule"):
            self._inner.schedule(msg)
        else:
            self.info(f"[SCHEDULE] {msg}")

    def report(self, msg: str):
        if hasattr(self._inner, "report"):
            self._inner.report(msg)
        else:
            self.info(f"[REPORT] {msg}")

    def stream(self, msg: str):
        if hasattr(self._inner, "stream"):
            self._inner.stream(msg)
        else:
            self.info(f"[STREAM] {msg}")

    def add_metadata(self, key: str, value: str):
        if hasattr(self._inner, "add_metadata"):
            self._inner.add_metadata(key, value)
        elif hasattr(self._inner, "add_tag"):
            self._inner.add_tag(key, value)



def ensure_safe_logger(logger: Optional[ILogger]) -> ILogger:
    """Ensures a valid logger is returned, falling back to DefaultLogger if None."""
    if logger is None:
        return DefaultLogger()
    return logger
