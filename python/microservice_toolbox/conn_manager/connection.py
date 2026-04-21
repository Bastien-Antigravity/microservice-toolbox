import threading
import time
from typing import TYPE_CHECKING

from .errors import WriteFailedError

if TYPE_CHECKING:
    from .manager import NetworkManager


class ManagedConnection:
    """
    ManagedConnection wraps a connection and handles automatic reconnection.

    It provides a 'self-healing' interface: if a write fails, it automatically
    triggers a background recovery and retries the operation (if applicable).
    Reconnection logic follows the parent NetworkManager's backoff policy.
    """
    def __init__(self, ip: str, port: str, public_ip: str, profile: str, nm: "NetworkManager"):
        self.ip = ip
        self.port = port
        self.public_ip = public_ip
        self.profile = profile
        self.nm = nm
        self.current_conn = None
        self._reconnecting = False
        self._lock = threading.Lock()

    def write(self, data: bytes):
        """
        Writes data to the connection, attempting reconnection if it fails.
        """
        with self._lock:
            # If no connection, try to reconnect immediately (blocking)
            if self.current_conn is None:
                self._lock.release()
                try:
                    self.reconnect()
                finally:
                    self._lock.acquire()

            try:
                # Assuming safesocket has a 'send' method
                return self.current_conn.send(data)
            except Exception as e:
                print(f"ManagedConnection: Write failed ({e}). Reconnecting...")
                try:
                    self.current_conn.close()
                except Exception:
                    pass
                self.current_conn = None

                # Reconnect and retry once
                self._lock.release()
                try:
                    self.reconnect()
                except Exception as re_err:
                    raise WriteFailedError(f"base write error: {e}; reconnect error: {re_err}")
                finally:
                    self._lock.acquire()

                if self.current_conn is None:
                    raise WriteFailedError("reconnection succeeded but current_conn is still None")
                return self.current_conn.send(data)

    def close(self):
        """
        Closes the underlying connection.
        """
        with self._lock:
            if self.current_conn:
                try:
                    self.current_conn.close()
                finally:
                    self.current_conn = None

    def reconnect(self):
        """
        Indefinitely attempts to reconnect with exponential backoff.
        """
        with self._lock:
            if self._reconnecting:
                # Wait for current reconnection
                while True:
                    self._lock.release()
                    time.sleep(0.1)
                    self._lock.acquire()
                    if self.current_conn is not None:
                        return
                    if not self._reconnecting:
                        self._reconnecting = True
                        break
            else:
                self._reconnecting = True

        delay = self.nm.base_delay
        i = 0

        while True:
            try:
                conn = self.nm.establish_connection(self.ip, self.port, self.public_ip, self.profile)
                print(f"ManagedConnection: Reconnected to {self.ip}:{self.port}")
                with self._lock:
                    self.current_conn = conn
                    self._reconnecting = False
                return
            except Exception as e:
                # Report failure to the optional hook
                if self.nm.on_error:
                    self.nm.on_error(i + 1, e, "NetworkManager",
                                     f"Failed to recover connection to {self.ip}:{self.port}")

                time.sleep(delay)
                delay *= 2
                i += 1
                if delay > self.nm.max_delay:
                    delay = self.nm.max_delay
