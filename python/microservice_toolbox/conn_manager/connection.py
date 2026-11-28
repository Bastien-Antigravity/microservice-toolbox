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
from typing import TYPE_CHECKING as typeChecking, Any as typeAny, Optional as typeOptional, Tuple as typeTuple

from .errors import MaxRetriesReachedError, NoConnectionError, WriteFailedError

if typeChecking:
    from .manager import NetworkManager

# -----------------------------------------------------------------------------------------------


class Endpoint:
    """Immutable destination coordinates holding pre-formatted Address."""

    __slots__ = ("ip", "port", "public_ip", "profile", "address")

    def __init__(self, ip: str, port: str, public_ip: str = "", profile: str = ""):
        self.ip = ip
        self.port = port
        self.public_ip = public_ip
        self.profile = profile
        self.address = f"{ip}:{port}"


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
        app_config: typeOptional[typeAny] = None,
        capability: typeOptional[str] = None,
    ):
        self.endpoint = Endpoint(ip, port, public_ip, profile)
        self.nm = nm
        self.app_config = app_config or (nm.app_config if nm else None)
        self.capability = capability
        self.current_conn = None
        self._reconnecting = False
        self._closed = False
        self._lock = threadingLock()

    # -----------------------------------------------------------------------------------------------

    def update_endpoint(self, ip: str, port: str) -> None:
        """Atomically updates the connection target coordinates."""
        ep = self.endpoint
        self.endpoint = Endpoint(ip, port, ep.public_ip, ep.profile)

    # -----------------------------------------------------------------------------------------------

    def get_endpoint(self) -> typeTuple[str, str]:
        """Returns current target coordinates."""
        ep = self.endpoint
        return ep.ip, ep.port

    # -----------------------------------------------------------------------------------------------

    def _current_endpoint(self) -> Endpoint:
        """Returns the active Endpoint, refreshing from AppConfig if bound to a capability."""
        ep = self.endpoint
        if self.app_config is not None and self.capability:
            try:
                new_addr = self.app_config.get_listen_addr(self.capability)
                if new_addr != ep.address and ":" in new_addr:
                    new_ip, new_port = new_addr.rsplit(":", 1)
                    self.update_endpoint(new_ip, new_port)
                    ep = self.endpoint
            except Exception:
                pass
        return ep

    # -----------------------------------------------------------------------------------------------

    def write(self, data: bytes) -> typeAny:
        """
        Writes data to the connection, attempting reconnection if it fails.
        """
        if self._closed:
            raise NoConnectionError(f"{self.Name} : connection is closed")

        conn = self.current_conn

        # If no connection, try to reconnect immediately (blocking)
        if conn is None:
            self.reconnect()
            conn = self.current_conn

        if conn is None:
            raise WriteFailedError(f"{self.Name} : connection is unavailable before write")

        try:
            # Assuming safesocket has a 'send' method
            return conn.send(data)
        except Exception as e:
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
            self._closed = True
            if self.current_conn:
                try:
                    self.current_conn.close()
                finally:
                    self.current_conn = None

    # -----------------------------------------------------------------------------------------------

    def reconnect(self) -> None:
        """
        Indefinitely attempts to reconnect with exponential backoff.
        """
        if self._closed:
            raise NoConnectionError(f"{self.Name} : connection is closed")

        while True:
            with self._lock:
                if self._closed:
                    raise NoConnectionError(f"{self.Name} : connection is closed")
                if not self._reconnecting:
                    self._reconnecting = True
                    break
                if self.current_conn is not None:
                    return
            timeSleep(0.1)

        i = 0

        while True:
            if self._closed:
                with self._lock:
                    self._reconnecting = False
                raise NoConnectionError(f"{self.Name} : connection is closed")

            attempt = i + 1
            ep = self._current_endpoint()

            try:
                conn = self.nm.establish_connection(ep.ip, ep.port, ep.public_ip, ep.profile)
                with self._lock:
                    if self._closed:
                        self._reconnecting = False
                        try:
                            conn.close()
                        except Exception:
                            pass
                        raise NoConnectionError(f"{self.Name} : connection closed during reconnect")
                    self.current_conn = conn
                    self._reconnecting = False
                self.nm.logger.info(f"{self.Name} : Reconnected to {ep.address}")
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

