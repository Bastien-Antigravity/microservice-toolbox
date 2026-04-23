#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
NetworkManager handles reliable connection establishment with retries.
Implements resilient strategies including backoff, jitter, and unified error reporting.

DATA FLOW:
1. Attempts to establish connection via EstablishConnection.
2. If failure occurs, calculates backoff/jitter and retries until max_retries or success.
3. Provides blocking and non-blocking entry points for connection management.

KEY PARAMETERS:
- max_retries: Support for infinite retries (-1).
- base_delay_ms: Initial delay before first retry.
- jitter: Randomness factor (0.0 to 1.0).
"""

from enum import IntEnum
from math import pow as mathPow
from random import uniform as randomUniform
from time import sleep as timeSleep
from typing import Any, Callable, Optional

try:
    from safesocket import safesocket
except ImportError:
    # Handle the case where safesocket is not installed/linked yet
    safesocket = None

from ..utils.logger import ILogger, ensure_safe_logger
from .connection import ManagedConnection
from .errors import MaxRetriesReachedError

OnErrorHandler = Callable[[int, Exception, str, str], None]
 
 
class ConnectionMode(IntEnum):
    """
    Defines how the manager handles the initial connection.
    """
 
    BLOCKING = 0
    NON_BLOCKING = 1
    INDEFINITE = 2

# -----------------------------------------------------------------------------------------------


class NetworkManager:
    """
    NetworkManager handles reliable connection establishment with retries.
    """

    Name = "NetworkManager"

    # -----------------------------------------------------------------------------------------------

    def __init__(
        self,
        max_retries: int = 5,
        base_delay_ms: int = 200,
        max_delay_ms: int = 5000,
        connect_timeout_ms: int = 2000,
        backoff: float = 2.0,
        jitter: float = 0.0,
        on_error: Optional[OnErrorHandler] = None,
        logger: Optional[ILogger] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay_ms / 1000.0
        self.max_delay = max_delay_ms / 1000.0
        self.connect_timeout = connect_timeout_ms / 1000.0
        self.backoff = backoff
        self.jitter = jitter
        self.on_error = on_error
        self.logger = ensure_safe_logger(logger)

    # -----------------------------------------------------------------------------------------------

    def establish_connection(self, ip: str, port: str, public_ip: str, profile: str) -> Any:
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

    # -----------------------------------------------------------------------------------------------

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
                delay = self.base_delay * mathPow(self.backoff, i)
                if delay > self.max_delay:
                    delay = self.max_delay

                # Apply jitter
                if self.jitter > 0:
                    delay += randomUniform(0, self.jitter * delay)

                self.logger.info(
                    "{0} : Initial connection to {1} failed: {2}. Retrying in {3:.2f}s...".format(
                        self.Name, address, e, delay
                    )
                )
                timeSleep(delay)
                i += 1

        raise MaxRetriesReachedError(f"{address} after {self.max_retries} attempts (last error: {last_err})")

    # -----------------------------------------------------------------------------------------------

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

    # -----------------------------------------------------------------------------------------------

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
                    self.on_error(1, e, "NetworkManager", f"Failed to connect to {ip}:{port} in background")

        thread = threading.Thread(target=run_reconnect, daemon=True)
        thread.start()
 
        return mc
 
    # -----------------------------------------------------------------------------------------------
 
    def connect(self, ip: str, port: str, public_ip: str, profile: str, mode: ConnectionMode) -> ManagedConnection:
        """
        Establishes a connection using the specified mode.
        """
        if mode == ConnectionMode.BLOCKING:
            try:
                return self.connect_with_retry(ip, port, public_ip, profile)
            except Exception:
                # To match Go behavior, we return the mc even if it failed?
                # Actually Go returns mc, _ = connect_with_retry
                return ManagedConnection(ip, port, public_ip, profile, self)
        elif mode == ConnectionMode.NON_BLOCKING:
            return self.connect_non_blocking(ip, port, public_ip, profile)
        elif mode == ConnectionMode.INDEFINITE:
            return self.connect_blocking(ip, port, public_ip, profile)
        else:
            return self.connect_blocking(ip, port, public_ip, profile)


# -----------------------------------------------------------------------------------------------


def new_network_manager(
    max_retries: int = 5,
    base_delay_ms: int = 200,
    max_delay_ms: int = 5000,
    connect_timeout_ms: int = 2000,
    backoff: float = 2.0,
    jitter: float = 0.0,
    on_error: Optional[OnErrorHandler] = None,
) -> NetworkManager:
    """Semantic helper to match Go NewNetworkManager()."""
    return NetworkManager(max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter, on_error)


# -----------------------------------------------------------------------------------------------


def new_network_manager_with_logger(
    max_retries: int = 5,
    base_delay_ms: int = 200,
    max_delay_ms: int = 5000,
    connect_timeout_ms: int = 2000,
    backoff: float = 2.0,
    jitter: float = 0.0,
    on_error: Optional[OnErrorHandler] = None,
    logger: Optional[ILogger] = None,
) -> NetworkManager:
    """Semantic helper to match Go NewNetworkManagerWithLogger()."""
    return NetworkManager(
        max_retries, base_delay_ms, max_delay_ms, connect_timeout_ms, backoff, jitter, on_error, logger
    )
 
 
# -----------------------------------------------------------------------------------------------
# Strategies
 
 
def new_critical_strategy(logger: Optional[ILogger] = None) -> NetworkManager:
    """
    Creates a manager configured for critical services:
    Infinite retries, aggressive backoff.
    """
    return new_network_manager_with_logger(-1, 200, 10000, 5000, 2.0, 0.2, None, logger)
 
 
def new_standard_strategy(logger: Optional[ILogger] = None) -> NetworkManager:
    """
    Creates a manager for standard services:
    Limited retries, moderate backoff.
    """
    return new_network_manager_with_logger(10, 500, 30000, 5000, 1.5, 0.1, None, logger)
 
 
def new_performance_strategy(logger: Optional[ILogger] = None) -> NetworkManager:
    """
    Creates a manager for high-performance services:
    Short timeouts, low delay, background reconnection.
    """
    return new_network_manager_with_logger(-1, 100, 2000, 1000, 1.2, 0.0, None, logger)
