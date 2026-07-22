#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
Provides cross-platform process locking using file locking to prevent multiple
instances of the same service/command from running concurrently.

DATA FLOW:
1. Process attempts to acquire a lock file in the system temp directory.
2. Uses fcntl.flock on Unix (macOS, Linux) and msvcrt.locking on Windows.
3. If successful, writes its PID to the lock file.
4. On exit or crash, the OS releases the lock.
"""

import os
import sys
import tempfile
from typing import Optional, Any

_active_locks = {}

class ProcessLock:
    """
    Cross-platform process lock using advisory file locking.
    """
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.lock_path = os.path.join(tempfile.gettempdir(), f"antigravity_{service_name}.lock")
        self.lock_file: Optional[Any] = None

    def acquire(self) -> bool:
        """
        Attempts to acquire the lock. Returns True if successful, False otherwise.
        """
        try:
            # Open the file in 'a+' mode so we don't truncate it before locking,
            # which prevents overwriting the running instance's PID file.
            self.lock_file = open(self.lock_path, "a+")
            
            if os.name == "nt":
                import msvcrt
                try:
                    # Windows requires seeking to 0 and locking a specific range
                    self.lock_file.seek(0)
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                except (OSError, IOError):
                    self.lock_file.close()
                    self.lock_file = None
                    return False
            else:
                import fcntl
                try:
                    # Unix flock with non-blocking exclusive lock
                    fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, IOError, BlockingIOError):
                    self.lock_file.close()
                    self.lock_file = None
                    return False

            # Lock acquired successfully! Now truncate and write current PID.
            try:
                self.lock_file.seek(0)
                self.lock_file.truncate(0)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.flush()
            except Exception:
                # Failing to write the PID is not fatal, but we keep the lock
                pass

            return True

        except Exception:
            if self.lock_file:
                try:
                    self.lock_file.close()
                except Exception:
                    pass
                self.lock_file = None
            return False

    def release(self) -> None:
        """
        Releases the lock.
        """
        if self.lock_file:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.lock_file.seek(0)
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
            except Exception:
                pass
            finally:
                self.lock_file = None
                try:
                    os.unlink(self.lock_path)
                except Exception:
                    pass


def prevent_double_start(service_name: str, logger: Optional[Any] = None) -> ProcessLock:
    """
    Ensures that only a single instance of the service is running.
    If already running, logs/prints a message and exits the program.
    """
    lock = ProcessLock(service_name)
    if not lock.acquire():
        msg = f"Process already running: {service_name} (lock file: {lock.lock_path})"
        if logger:
            logger.critical(msg)
        else:
            sys.stderr.write(f"CRITICAL: {msg}\n")
        sys.exit(1)
        
    # Store globally to prevent garbage collection of the file object/lock
    _active_locks[service_name] = lock
    return lock
