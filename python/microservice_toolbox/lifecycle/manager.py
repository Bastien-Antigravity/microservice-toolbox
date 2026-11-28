#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Manages the application lifecycle and coordinates graceful shutdown procedures.
Captures OS signals and executes registered cleanup handlers in reverse order (LIFO).

DATA FLOW:
1. Components register cleanup functions with the manager.
2. Manager blocks until a termination signal (SIGINT, SIGTERM) or shutdown request.
3. Registered handlers are executed in LIFO order, ensuring resources are released cleanly.

KEY PARAMETERS:
- ShutdownFunc: A callable that returns None, used for cleanup operations.
"""

from signal import (
    SIGINT as sigSIGINT,
    SIGTERM as sigSIGTERM,
    Signals as sigSignals,
    signal as sigSignal,
)
from threading import Event as threadingEvent, Lock as threadingLock
from typing import (
    Callable as typeCallable,
    List as typeList,
    Optional as typeOptional,
    Tuple as typeTuple,
)

from ..logger import Logger, ensure_safe_logger

# -----------------------------------------------------------------------------------------------

ShutdownFunc = typeCallable[[], None]

# -----------------------------------------------------------------------------------------------


class LifecycleManager:
    """
    LifecycleManager handles application lifecycle and graceful shutdown.
    Captures signals (SIGINT, SIGTERM) and executes registered cleanup functions in LIFO order.
    """

    Name = "LifecycleManager"

    # -----------------------------------------------------------------------------------------------

    def __init__(self, logger: typeOptional[Logger] = None):
        self._lock = threadingLock()
        self._cleanups: typeList[typeTuple[str, ShutdownFunc]] = []
        self.logger = ensure_safe_logger(logger)
        self._shutdown_event = threadingEvent()

    # -----------------------------------------------------------------------------------------------

    def register(self, name: str, fn: ShutdownFunc) -> None:
        """Adds a cleanup function to the shutdown list safely under lock."""
        with self._lock:
            self._cleanups.append((name, fn))

    # -----------------------------------------------------------------------------------------------

    def request_shutdown(self) -> None:
        """Signals Wait() to wake up and execute registered cleanups."""
        self._shutdown_event.set()

    # -----------------------------------------------------------------------------------------------

    def wait(self) -> None:
        """Blocks until SIGINT, SIGTERM, or request_shutdown(), then executes cleanups."""

        def signal_handler(sig, frame):
            sig_name = sigSignals(sig).name
            self.logger.info("{0} : Received signal {1}. Initiating graceful shutdown...".format(self.Name, sig_name))
            self._shutdown_event.set()

        sigSignal(sigSIGINT, signal_handler)
        sigSignal(sigSIGTERM, signal_handler)

        try:
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=1.0)
        except (KeyboardInterrupt, SystemExit):
            pass

        self.execute_cleanups()

    # -----------------------------------------------------------------------------------------------

    def execute_cleanups(self) -> None:
        """Executes registered cleanups in reverse order (LIFO) and drains the hook list."""
        with self._lock:
            hooks = list(self._cleanups)
            self._cleanups.clear()

        for name, fn in reversed(hooks):
            try:
                self.logger.info("{0} : Running cleanup '{1}'...".format(self.Name, name))
                fn()
            except Exception as e:
                self.logger.error("{0} : Cleanup '{1}' failed: {2}".format(self.Name, name, e))

        self.logger.info("{0} : Clean shutdown completed.".format(self.Name))

    _execute_cleanups = execute_cleanups


# -----------------------------------------------------------------------------------------------


def new_manager() -> LifecycleManager:
    """Creates a new lifecycle manager with default logging."""
    return LifecycleManager()


# -----------------------------------------------------------------------------------------------


def new_manager_with_logger(logger: Logger) -> LifecycleManager:
    """Creates a new lifecycle manager with an explicit logger."""
    return LifecycleManager(logger)
