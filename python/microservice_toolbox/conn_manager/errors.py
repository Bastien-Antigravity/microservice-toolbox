#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Domain-specific exception hierarchy for network connection management, retries, and write failures.

DATA FLOW:
1. Input: Low-level socket, protocol, or timeout error conditions.
2. Logic: Encapsulates connection lifecycle failures into strongly-typed exceptions.
3. Output: Raised to callers of NetworkManager and ManagedConnection.

KEY PARAMETERS:
- None (Domain Exception Definitions).
"""


# -----------------------------------------------------------------------------------------------
# ### CONNECTION MANAGER EXCEPTIONS ###
# -----------------------------------------------------------------------------------------------

class ConnectionManagerError(Exception):
    """Base class for connection manager errors."""

    pass


class ConnectionRefusedError(ConnectionManagerError):
    """Raised when the target address actively rejects the connection."""

    pass


class MaxRetriesReachedError(ConnectionManagerError):
    """Raised when the network manager gives up after the configured number of attempts."""

    pass


class NoConnectionError(ConnectionManagerError):
    """Raised when an operation is attempted on a nil or closed connection."""

    pass


class WriteFailedError(ConnectionManagerError):
    """Raised when data could not be sent over the socket."""

    pass
