#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides cross-platform process locking using file locking to prevent multiple
instances of the same service/command from running concurrently.

DATA FLOW:
1. Input: Lock name string representing the unique service instance.
2. Logic: Acquires OS-level file lock (fcntl on Unix, msvcrt on Windows) and records PID.
3. Output: Acquired ProcessLock context manager or raises RuntimeError.

KEY PARAMETERS:
- lock_name: Unique identifier for the process lock file.
- fail_fast: If True, raises RuntimeError immediately instead of waiting for lock.
"""

from os import (
    O_RDWR as osO_RDWR,
    close as osClose,
    getpid as osGetpid,
    kill as osKill,
    name as osName,
    open as osOpen,
    unlink as osUnlink,
)
from os.path import exists as osPathExists, join as osPathJoin
from sys import exit as sysExit, stderr as sysStderr
from tempfile import gettempdir as tempfileGetTempDir
from typing import Any, Optional

if osName == "nt":
    from ctypes import windll as ctypesWindll
    from msvcrt import (
        LK_NBLCK as msvcrtLK_NBLCK,
        LK_UNLCK as msvcrtLK_UNLCK,
        locking as msvcrtLocking,
    )
else:
    from fcntl import (
        LOCK_EX as fcntlLOCK_EX,
        LOCK_NB as fcntlLOCK_NB,
        LOCK_UN as fcntlLOCK_UN,
        flock as fcntlFlock,
    )

_active_locks = {}


class ProcessLock:
    """
    Cross-platform process lock using advisory file locking.
    """
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.lock_path = osPathJoin(tempfileGetTempDir(), f"antigravity_{service_name}.lock")
        self.lock_file: Optional[Any] = None

    def acquire(self) -> bool:
        """
        Attempts to acquire the lock. Returns True if successful, False otherwise.
        """
        try:
            # Open the file in 'a+' mode so we don't truncate it before locking,
            # which prevents overwriting the running instance's PID file.
            self.lock_file = open(self.lock_path, "a+")

            if osName == "nt":
                try:
                    # Windows requires seeking to 0 and locking a specific range
                    self.lock_file.seek(0)
                    msvcrtLocking(self.lock_file.fileno(), msvcrtLK_NBLCK, 1)
                except (OSError, IOError):
                    self.lock_file.close()
                    self.lock_file = None
                    return False
            else:
                try:
                    # Unix flock with non-blocking exclusive lock
                    fcntlFlock(self.lock_file, fcntlLOCK_EX | fcntlLOCK_NB)
                except (OSError, IOError, BlockingIOError):
                    self.lock_file.close()
                    self.lock_file = None
                    return False

            # Lock acquired successfully! Now truncate and write current PID.
            try:
                self.lock_file.seek(0)
                self.lock_file.truncate(0)
                self.lock_file.write(str(osGetpid()))
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
                if osName == "nt":
                    self.lock_file.seek(0)
                    msvcrtLocking(self.lock_file.fileno(), msvcrtLK_UNLCK, 1)
                else:
                    fcntlFlock(self.lock_file, fcntlLOCK_UN)
                self.lock_file.close()
            except Exception:
                pass
            finally:
                self.lock_file = None
                try:
                    osUnlink(self.lock_path)
                except Exception:
                    pass

    def __enter__(self) -> "ProcessLock":
        if not self.acquire():
            raise RuntimeError(f"Could not acquire process lock for '{self.service_name}'. Another instance is running.")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


# -----------------------------------------------------------------------------------------------


def is_pid_alive(pid: int) -> bool:
    """
    Cross-platform check to determine if a process with the given PID is running.
    Works natively on Windows, macOS, and Linux without external dependencies.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False

    if osName == "nt":
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypesWindll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        ERROR_ACCESS_DENIED = 5
        return kernel32.GetLastError() == ERROR_ACCESS_DENIED
    else:
        try:
            osKill(pid, 0)
            return True
        except PermissionError:
            # Process exists, but current user lacks permission to send signals to it
            return True
        except (ProcessLookupError, OSError):
            return False


# -----------------------------------------------------------------------------------------------


def is_process_running(service_name: str) -> Optional[dict]:
    """
    Non-destructively inspects whether a service is currently running.
    Returns None if not running.
    If running, returns a dictionary with metadata:
      {'pid': int|None, 'alive': bool, 'lock_path': str}
    """
    lock_path = osPathJoin(tempfileGetTempDir(), f"antigravity_{service_name}.lock")
    if not osPathExists(lock_path):
        return None

    pid = None
    try:
        with open(lock_path, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                pid = int(content)
    except Exception:
        pass

    # Non-destructive lock acquisition test (does not truncate or unlink)
    lock_held = False
    try:
        fd = osOpen(lock_path, osO_RDWR)
        try:
            if osName == "nt":
                msvcrtLocking(fd, msvcrtLK_NBLCK, 1)
                msvcrtLocking(fd, msvcrtLK_UNLCK, 1)
            else:
                fcntlFlock(fd, fcntlLOCK_EX | fcntlLOCK_NB)
                fcntlFlock(fd, fcntlLOCK_UN)
        except (OSError, IOError, BlockingIOError):
            lock_held = True
        finally:
            osClose(fd)
    except Exception:
        lock_held = True

    if not lock_held:
        # File existed on disk but flock was free -> stale lock file!
        if pid:
            if not is_pid_alive(pid):
                try:
                    osUnlink(lock_path)
                except Exception:
                    pass
        return None

    # Lock is genuinely held by a running process
    is_alive = is_pid_alive(pid) if pid else False

    return {
        "pid": pid,
        "alive": is_alive,
        "lock_path": lock_path,
    }


# -----------------------------------------------------------------------------------------------


def prevent_double_start(service_name: str, logger: Optional[Any] = None) -> ProcessLock:
    """
    Ensures that only a single instance of the service is running.
    If already running, logs/prints a message and exits the program.
    """
    lock = ProcessLock(service_name)
    if not lock.acquire():
        info = is_process_running(service_name)
        pid_info = f" (PID: {info['pid']})" if info and info.get("pid") else ""
        msg = f"Process already running: {service_name}{pid_info} (lock file: {lock.lock_path})"
        if logger:
            logger.critical(msg)
        else:
            sysStderr.write(f"CRITICAL: {msg}\n")
        sysExit(1)

    # Store globally to prevent garbage collection of the file object/lock
    _active_locks[service_name] = lock
    return lock
