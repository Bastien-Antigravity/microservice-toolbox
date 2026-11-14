#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
ManagedConnection wraps a connection and handles automatic reconnection.
Provides a 'self-healing' interface that triggers background recovery upon failure.

DATA FLOW:
1. Operations (write) check for active connection.
2. If failure occurs, triggers reconnect loop.
3. Retries operation once connection is restored.

KEY PARAMETERS:
- ip/port: Targeted connection endpoint.
- nm: Parent NetworkManager providing reconnection policies.
"""

from threading import Lock as threadingLock
from time import sleep as timeSleep
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Union

from .errors import MaxRetriesReachedError, WriteFailedError

if TYPE_CHECKING:
    from .manager import NetworkManager

ReloadHandler = Callable[[int], Tuple[str, str]]

# -----------------------------------------------------------------------------------------------


class Endpoint:
    """Immutable destination coordinates holding pre-formatted Address."""

    __slots__ = ("ip", "port", "public_ip", "profile", "address")

    def __init__(self, ip: str, port: str, public_ip: str = "", profile: str = ""):
        self.ip = ip.strip('"')
        self.port = port.strip('"')
        self.public_ip = public_ip.strip('"') if public_ip else ""
        self.profile = profile.strip('"') if profile else ""
        self.address = f"{self.ip}:{self.port}"


# -----------------------------------------------------------------------------------------------


class ManagedConnection:
    """
    ManagedConnection wraps a connection and handles automatic reconnection.
    """

    Name = "ManagedConnection"

    # -----------------------------------------------------------------------------------------------

    def __init__(
        self,
        ip: str,
        port: str,
        public_ip: str,
        profile: str,
        nm: "NetworkManager",
        on_reload: Optional[Callable[..., Any]] = None,
        app_config: Optional[Any] = None,
        capability: Optional[str] = None,
    ):
        self.endpoint = Endpoint(ip, port, public_ip, profile)
        self.nm = nm
        self.on_reload = on_reload or (nm.on_reload_config if nm else None)
        self.app_config = app_config or (getattr(nm, "app_config", None) if nm else None)
        self.capability = capability
        self.current_conn = None
        self._reconnecting = False
        self._lock = threadingLock()

    # -----------------------------------------------------------------------------------------------

    def set_reload_handler(self, handler: Optional[Callable[..., Any]]) -> None:
        """Sets or updates the configuration reload handler."""
        self.on_reload = handler

    # -----------------------------------------------------------------------------------------------

    def update_endpoint(self, ip: str, port: str) -> None:
        """Atomically updates the connection target coordinates."""
        ep = self.endpoint
        self.endpoint = Endpoint(ip, port, ep.public_ip, ep.profile)

    # -----------------------------------------------------------------------------------------------

    def get_endpoint(self) -> Tuple[str, str]:
        """Returns current target coordinates."""
        ep = self.endpoint
        return ep.ip, ep.port

    # -----------------------------------------------------------------------------------------------

    def _trigger_reload(self, attempt: int) -> None:
        """
        Triggers config reload or callback when reconnection attempts reach multiples of 3.
        """
        with self._lock:
            ac = self.app_config
            cap = self.capability
            handler = self.on_reload

        # 1. Direct AppConfig resolution if bound to capability
        if ac and cap:
            self.nm.logger.warning(
                f"{self.Name} : 3 failed connection attempts reached (attempt {attempt}). Synchronizing config from server..."
            )
            try:
                if hasattr(ac, "sync"):
                    ac.sync()
                new_addr = ac.get_listen_addr(cap)
                if ":" in new_addr:
                    new_ip, new_port = new_addr.rsplit(":", 1)
                    self.update_endpoint(new_ip, new_port)
                    self.nm.logger.info(
                        f"{self.Name} : Target address for capability {cap} updated to {new_ip}:{new_port} following config sync"
                    )
                    return
            except Exception as e:
                self.nm.logger.warning(f"{self.Name} : Config sync for capability {cap} failed: {e}")
                return

        # 2. Custom ReloadHandler callback fallback (for raw IP:port connections)
        if handler is None:
            return

        self.nm.logger.warning(
            f"{self.Name} : 3 failed connection attempts reached (attempt {attempt}). Reloading configuration..."
        )

        try:
            new_ip, new_port = handler(attempt)
            self.update_endpoint(new_ip, new_port)
            self.nm.logger.info(f"{self.Name} : Target address updated to {new_ip}:{new_port} following config reload")
        except Exception as e:
            self.nm.logger.warning(f"{self.Name} : Reload configuration attempt {attempt} failed: {e}")

    # -----------------------------------------------------------------------------------------------

    def write(self, data: bytes) -> Any:
        """
        Writes data to the connection, attempting reconnection if it fails.
        """
        with self._lock:
            conn = self.current_conn

        # If no connection, try to reconnect immediately (blocking)
        if conn is None:
            self.reconnect()
            with self._lock:
                conn = self.current_conn

        if conn is None:
            raise WriteFailedError(f"{self.Name} : connection is unavailable before write")

        try:
            # Assuming safesocket has a 'send' method
            return conn.send(data)
        except Exception as e:
            if self.nm and getattr(self.nm, "logger", None):
                self.nm.logger.warning("{0} : Write failed ({1}). Reconnecting...".format(self.Name, e))

            with self._lock:
                if self.current_conn is conn:
                    try:
                        self.current_conn.close()
                    except Exception:
                        pass
                    self.current_conn = None

            # Reconnect and retry once
            try:
                self.reconnect()
            except Exception as re_err:
                raise WriteFailedError(f"base write error: {e}; reconnect error: {re_err}")

            with self._lock:
                conn = self.current_conn

            if conn is None:
                raise WriteFailedError("reconnection succeeded but current_conn is still None")
            return conn.send(data)

    # -----------------------------------------------------------------------------------------------

    def close(self) -> None:
        """
        Closes the underlying connection.
        """
        with self._lock:
            if self.current_conn:
                try:
                    self.current_conn.close()
                finally:
                    self.current_conn = None

    # -----------------------------------------------------------------------------------------------

    def reconnect(self) -> None:
        """
        Indefinitely attempts to reconnect with exponential backoff.
        Triggers reload handler every 3 failed attempts to refresh coordinates.
        """
        while True:
            with self._lock:
                if not self._reconnecting:
                    self._reconnecting = True
                    break
                if self.current_conn is not None:
                    return
            timeSleep(0.1)

        i = 0

        while True:
            attempt = i + 1
            if attempt % 3 == 0:
                self._trigger_reload(attempt)

            ep = self.endpoint

            try:
                conn = self.nm.establish_connection(ep.ip, ep.port, ep.public_ip, ep.profile)
                if self.nm and getattr(self.nm, "logger", None):
                    self.nm.logger.info(f"{self.Name} : Reconnected to {ep.address}")
                with self._lock:
                    self.current_conn = conn
                    self._reconnecting = False
                return
            except Exception as e:
                # Check if we reached max retries (if not infinite)
                if self.nm.max_retries != -1 and i >= self.nm.max_retries:
                    with self._lock:
                        self._reconnecting = False
                    raise MaxRetriesReachedError(
                        f"{self.Name} : reached max retries {self.nm.max_retries} for {ep.address}"
                    )

                # Report failure to the optional hook
                if self.nm.on_error:
                    self.nm.on_error(
                        attempt, e, "NetworkManager", f"Failed to recover connection to {ep.address}"
                    )

                delay = self.nm.get_next_delay(i)
                timeSleep(delay)
                i += 1

