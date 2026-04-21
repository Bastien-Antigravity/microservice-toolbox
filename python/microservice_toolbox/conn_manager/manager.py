import math
import random
import time
from typing import Callable, Optional

try:
    from safesocket import safesocket
except ImportError:
    # Handle the case where safesocket is not installed/linked yet
    safesocket = None

from ..utils.logger import ILogger, ensure_safe_logger
from .connection import ManagedConnection
from .errors import MaxRetriesReachedError

OnErrorHandler = Callable[[int, Exception, str, str], None]

class NetworkManager:
    """
    NetworkManager handles reliable connection establishment with retries.

    It implements a resilient strategy using:
    - Multiplicative Backoff: Increasing delay between attempts.
    - Randomized Jitter: Prevents thundering herd issues in large fleets.
    - Context-Aware Recovery: Unified error reporting via on_error.
    """
    def __init__(
        self,
        max_retries: int = 5,
        base_delay_ms: int = 200,
        max_delay_ms: int = 5000,
        connect_timeout_ms: int = 2000,
        backoff: float = 2.0,
        jitter: float = 0.0,
        on_error: Optional[OnErrorHandler] = None,
        logger: Optional[ILogger] = None
    ):
        """
        :param on_error: Optional callback func(attempt, err, source, msg).
                         Triggers on every failure, including background recoveries.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay_ms / 1000.0
        self.max_delay = max_delay_ms / 1000.0
        self.connect_timeout = connect_timeout_ms / 1000.0
        self.backoff = backoff
        self.jitter = jitter
        self.on_error = on_error
        self.logger = ensure_safe_logger(logger)

    def establish_connection(self, ip: str, port: str, public_ip: str, profile: str):
        """
        Attempts a single connection to the resolved address.
        """
        if safesocket is None:
            raise ImportError("safesocket library not found")

        clean_ip = ip.strip('"')
        clean_port = port.strip('"')
        address = f"{clean_ip}:{clean_port}"

        # In Python safesocket.create returns a SafeSocket object
        return safesocket.create(profile, address, public_ip, "client", True)

    def connect_with_retry(self, ip: str, port: str, public_ip: str, profile: str) -> ManagedConnection:
        """
        Attempts to connect and returns a ManagedConnection.
        """
        mc = ManagedConnection(ip, port, public_ip, profile, self)

        clean_ip = ip.strip('"')
        clean_port = port.strip('"')
        address = f"{clean_ip}:{clean_port}"

        last_err = None
        i = 0
        while self.max_retries == -1 or i < self.max_retries:
            try:
                conn = self.establish_connection(ip, port, public_ip, profile)
                mc.current_conn = conn
                return mc
            except Exception as e:
                last_err = e
                # Report failure to the optional on_error hook
                if self.on_error:
                    self.on_error(i + 1, e, "NetworkManager", f"Initial connection failure to {address}")

                # Calculate backoff
                delay = self.base_delay * math.pow(self.backoff, i)
                if delay > self.max_delay:
                    delay = self.max_delay

                # Apply jitter
                if self.jitter > 0:
                    delay += random.uniform(0, self.jitter * delay)

                self.logger.info(f"ManagedConnection: Initial connection to {address} failed: {e}. "
                                 f"Retrying in {delay:.2f}s...")
                time.sleep(delay)
                i += 1

        raise MaxRetriesReachedError(f"{address} after {self.max_retries} attempts (last error: {last_err})")

    def connect_blocking(self, ip: str, port: str, public_ip: str, profile: str) -> ManagedConnection:
        """
        Indefinitely retries connection until successful and returns ManagedConnection.
        """
        mc = ManagedConnection(ip, port, public_ip, profile, self)

        try:
            mc.reconnect()
        except Exception as e:
            if self.on_error:
                self.on_error(1, e, "NetworkManager", f"Failed to connect to {ip}:{port}")

        return mc

    def connect_non_blocking(self, ip: str, port: str, public_ip: str, profile: str) -> ManagedConnection:
        """
        Immediately returns a ManagedConnection and attempts to connect in the background.
        """
        import threading
        mc = ManagedConnection(ip, port, public_ip, profile, self)

        def run_reconnect():
            try:
                mc.reconnect()
            except Exception as e:
                if self.on_error:
                    self.on_error(1, e, "NetworkManager",
                                  f"Failed to connect to {ip}:{port} in background")

        thread = threading.Thread(target=run_reconnect, daemon=True)
        thread.start()

        return mc

def new_network_manager(
    max_retries: int = 5,
    base_delay_ms: int = 200,
    max_delay_ms: int = 5000,
    connect_timeout_ms: int = 2000,
    backoff: float = 2.0,
    jitter: float = 0.0,
    on_error: Optional[OnErrorHandler] = None
) -> NetworkManager:
    return NetworkManager(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms,
                          backoff, jitter, on_error)

def new_network_manager_with_logger(
    max_retries: int = 5,
    base_delay_ms: int = 200,
    max_delay_ms: int = 5000,
    connect_timeout_ms: int = 2000,
    backoff: float = 2.0,
    jitter: float = 0.0,
    on_error: Optional[OnErrorHandler] = None,
    logger: Optional[ILogger] = None
) -> NetworkManager:
    return NetworkManager(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms,
                          backoff, jitter, on_error, logger)
