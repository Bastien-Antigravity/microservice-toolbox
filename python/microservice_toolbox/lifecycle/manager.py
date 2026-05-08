import signal
import sys
import threading
from typing import Callable, List, Optional
from ..utils.logger import ILogger, ensure_safe_logger

ShutdownFunc = Callable[[], None]

class LifecycleManager:
    """
    LifecycleManager handles application lifecycle and graceful shutdown.
    Capture signals (SIGINT, SIGTERM) and execute registered cleanup functions.
    """
    
    def __init__(self, logger: Optional[ILogger] = None):
        self._cleanups: List[tuple[str, ShutdownFunc]] = []
        self.logger = ensure_safe_logger(logger)
        self._shutdown_event = threading.Event()
        
    def register(self, name: str, fn: ShutdownFunc):
        """Adds a cleanup function to the list."""
        self._cleanups.append((name, fn))
        
    def wait(self):
        """Blocks until a SIGINT or SIGTERM is received, then executes cleanups."""
        
        def signal_handler(sig, frame):
            sig_name = signal.Signals(sig).name
            self.logger.info(f"Lifecycle: Received signal {sig_name}. Initiating graceful shutdown...")
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
        
    def _execute_cleanups(self):
        # Execute cleanups in reverse order (LIFO)
        for name, fn in reversed(self._cleanups):
            try:
                self.logger.info(f"Lifecycle: Running cleanup '{name}'...")
                fn()
            except Exception as e:
                self.logger.error(f"Lifecycle: Cleanup '{name}' failed: {e}")
                
        self.logger.info("Lifecycle: Clean shutdown completed.")

def new_manager() -> LifecycleManager:
    """Creates a new lifecycle manager with default logging."""
    return LifecycleManager()

def new_manager_with_logger(logger: ILogger) -> LifecycleManager:
    """Creates a new lifecycle manager with an explicit logger."""
    return LifecycleManager(logger)
