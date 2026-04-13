from typing import Protocol, runtime_checkable, Any, Optional
import sys
import os

@runtime_checkable
class Logger(Protocol):
    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
    def critical(self, msg: str) -> None: ...

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

    def debug(self, msg: str): self._print("DEBUG", "DefaultLogger", "logger.py", "24", msg)
    def info(self, msg: str): self._print("INFO", "DefaultLogger", "logger.py", "25", msg)
    def warning(self, msg: str): self._print("WARNING", "DefaultLogger", "logger.py", "26", msg)
    def error(self, msg: str): self._print("ERROR", "DefaultLogger", "logger.py", "27", msg)
    def critical(self, msg: str): self._print("CRITICAL", "DefaultLogger", "logger.py", "28", msg)

class UniLogger:
    """Wrapper for the compiled universal-logger."""
    def __init__(self, unilog_instance: Any):
        self._inner = unilog_instance

    def debug(self, msg: str): self._inner.debug(msg)
    def info(self, msg: str): self._inner.info(msg)
    def warning(self, msg: str): self._inner.warning(msg)
    def error(self, msg: str): self._inner.error(msg)
    def critical(self, msg: str): self._inner.critical(msg)

def EnsureSafeLogger(logger: Optional[Logger]) -> Logger:
    """Ensures a valid logger is returned, falling back to DefaultLogger if None."""
    if logger is None:
        return DefaultLogger()
    return logger
