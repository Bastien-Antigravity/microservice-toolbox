import time
import threading
from .errors import WriteFailedError

class ManagedConnection:
    """
    ManagedConnection wraps a connection and handles automatic reconnection.
    """
    def __init__(self, ip: str, port: str, public_ip: str, profile: str, nm: 'NetworkManager'):
        self.ip = ip
        self.port = port
        self.public_ip = public_ip
        self.profile = profile
        self.nm = nm
        self.current_conn = None
        self._lock = threading.Lock()

    def write(self, data: bytes):
        """
        Writes data to the connection, attempting reconnection if it fails.
        """
        with self._lock:
            # If no connection, try to reconnect immediately (blocking)
            if self.current_conn is None:
                self.reconnect()

            try:
                # Assuming safesocket has a 'send' method
                return self.current_conn.send(data)
            except Exception as e:
                print(f"ManagedConnection: Write failed ({e}). Reconnecting...")
                try:
                    self.current_conn.close()
                except:
                    pass
                self.current_conn = None

                # Reconnect and retry once
                try:
                    self.reconnect()
                    return self.current_conn.send(data)
                except Exception as re_err:
                    raise WriteFailedError(f"base write error: {e}; reconnect error: {re_err}")

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
        delay = self.nm.base_delay
        
        while True:
            try:
                conn = self.nm.establish_connection(self.ip, self.port, self.public_ip, self.profile)
                print(f"ManagedConnection: Reconnected to {self.ip}:{self.port}")
                self.current_conn = conn
                return
            except Exception as e:
                # Report failure to the optional on_error hook
                if self.nm.on_error:
                    self.nm.on_error("NetworkManager", "ManagedConnection.reconnect", e, f"Failed to recover connection to {self.ip}:{self.port}")
                
                time.sleep(delay)
                delay *= 2
                if delay > self.nm.max_delay:
                    delay = self.nm.max_delay
