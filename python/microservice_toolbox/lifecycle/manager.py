#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Manages the application lifecycle and coordinates graceful shutdown procedures.
Captures OS signals and executes registered cleanup handlers in reverse order (LIFO).

DATA FLOW:
1. Components register cleanup functions with the manager.
2. Manager blocks until a termination signal (SIGINT, SIGTERM) is received.
3. Registered handlers are executed, ensuring resources are released cleanly.

KEY PARAMETERS:
- ShutdownFunc: A callable that returns None, used for cleanup operations.
"""

import signal
import threading
from typing import Callable, List, Optional

from ..utils.logger import Logger, ensure_safe_logger

# -----------------------------------------------------------------------------------------------

ShutdownFunc = Callable[[], None]

# -----------------------------------------------------------------------------------------------


class LifecycleManager:
    """
    LifecycleManager handles application lifecycle and graceful shutdown.
    Capture signals (SIGINT, SIGTERM) and execute registered cleanup functions.
    """

    Name = "LifecycleManager"

    # -----------------------------------------------------------------------------------------------

    def __init__(self, logger: Optional[Logger] = None):
        self._cleanups: List[tuple[str, ShutdownFunc]] = []
        self.logger = ensure_safe_logger(logger)
        self._shutdown_event = threading.Event()

    # -----------------------------------------------------------------------------------------------

    def register(self, name: str, fn: ShutdownFunc) -> None:
        """Adds a cleanup function to the list."""
        self._cleanups.append((name, fn))

    # -----------------------------------------------------------------------------------------------

    def wait(self) -> None:
        """Blocks until a SIGINT or SIGTERM is received, then executes cleanups."""

        def signal_handler(sig, frame):
            sig_name = signal.Signals(sig).name
            self.logger.info("{0} : Received signal {1}. Initiating graceful shutdown...".format(self.Name, sig_name))
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Block until event is set
        try:
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=1.0)
        except (KeyboardInterrupt, SystemExit):
            pass

        self._execute_cleanups()

    # -----------------------------------------------------------------------------------------------

    def _execute_cleanups(self) -> None:
        """Execute cleanups in reverse order (LIFO)."""
        for name, fn in reversed(self._cleanups):
            try:
                self.logger.info("{0} : Running cleanup '{1}'...".format(self.Name, name))
                fn()
            except Exception as e:
                self.logger.error("{0} : Cleanup '{1}' failed: {2}".format(self.Name, name, e))

        self.logger.info("{0} : Clean shutdown completed.".format(self.Name))


# -----------------------------------------------------------------------------------------------


def new_manager() -> LifecycleManager:
    """Creates a new lifecycle manager with default logging."""
    return LifecycleManager()


# -----------------------------------------------------------------------------------------------


def new_manager_with_logger(logger: Logger) -> LifecycleManager:
    """Creates a new lifecycle manager with an explicit logger."""
    return LifecycleManager(logger)
