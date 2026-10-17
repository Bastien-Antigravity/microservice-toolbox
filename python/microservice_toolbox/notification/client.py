#!/usr/bin/env python
# coding:utf-8

"""
# -----------------------------------------------------------------------------------------------
# ESSENTIAL PROCESS:
# High-level client facade enabling L2 and L3 Python microservices to send direct,
# multi-channel notifications to notif-server via the libnotif CGO shared library bridge.
#
# DATA FLOW:
# L2/L3 Domain Event -> NotificationClient.send / send_alert -> libnotif FFI -> gRPC (Port 1027) -> notif-server
#
# KEY PARAMETERS:
# - app_config: Shared ecosystem AppConfig dynamically resolving notif_server gRPC capability.
# - target_addr: Target gRPC address (host:port) of notif-server.
# - logger: Unified ecosystem logger instance.
# -----------------------------------------------------------------------------------------------
"""

from asyncio import get_running_loop as asyncioGetRunningLoop
from concurrent.futures import ThreadPoolExecutor as concurrentThreadPoolExecutor
from ctypes import c_double as ctypesC_double, string_at as ctypesStringAt
from typing import Optional

from ..logger import Logger, ensure_safe_logger
from ..utils.lib_loader import load_libnotif

DEFAULT_TIMEOUT = 5.0

# Dedicated thread pool executor to safely execute CGO invocations across OS threads
_notif_executor = concurrentThreadPoolExecutor(max_workers=4)

# -----------------------------------------------------------------------------------------------
# NotificationClient
# -----------------------------------------------------------------------------------------------


class NotificationClient:
    """
    NotificationClient provides a thread-safe, resilient client for dispatching
    notifications directly from Python microservices to notif-server via libnotif.
    """

    def __init__(self, target_addr: str, logger: Optional[Logger] = None):
        """
        Initializes a NotificationClient pointing to a specific target address.
        """
        if not target_addr:
            raise ValueError("target_addr cannot be empty")
        self.target_addr = target_addr
        self.logger = ensure_safe_logger(logger)
        self.timeout = DEFAULT_TIMEOUT
        self._closed = False

        self._lib = load_libnotif()
        if not self._lib:
            raise RuntimeError("Could not load libnotif shared library from notif-server")

    # -----------------------------------------------------------------------------------------------

    @classmethod
    def from_config(cls, app_config, logger: Optional[Logger] = None) -> "NotificationClient":
        """
        Initializes a NotificationClient by dynamically resolving the notif_server
        capability address from the provided ecosystem AppConfig.
        Fails fast if the notif_server capability or its gRPC address is unresolvable.
        """
        safe_logger = ensure_safe_logger(logger)

        if app_config is None:
            raise ValueError("app_config cannot be None")

        try:
            addr = app_config.get_grpc_listen_addr("notif_server")
        except Exception as e:
            raise ValueError(f"failed to resolve notif_server gRPC address: {e}") from e

        if not addr:
            raise ValueError("failed to resolve notif_server gRPC address: address is empty")

        safe_logger.info(f"NotificationClient configured with target address: {addr}")
        return cls(target_addr=addr, logger=safe_logger)

    # -----------------------------------------------------------------------------------------------

    def set_timeout(self, timeout: float) -> None:
        """Sets default RPC dispatch timeout in seconds."""
        self.timeout = float(timeout)

    # -----------------------------------------------------------------------------------------------

    async def send(self, message: str, *tags: str) -> None:
        """
        1-line helper dispatching an untyped or informational notification
        with optional destination tags (e.g. 'telegram', 'discord').
        """
        await self.send_with_attachment("", message, "", *tags)

    # -----------------------------------------------------------------------------------------------

    async def send_alert(self, level: str, message: str, *tags: str) -> None:
        """
        Dispatches a categorized notification with a specific severity level
        (e.g., 'TRADE', 'CRITICAL', 'WARNING', 'REPORT', 'INFO') and optional tags.
        """
        await self.send_with_attachment(level, message, "", *tags)

    # -----------------------------------------------------------------------------------------------

    async def send_with_attachment(self, level: str, message: str, attachment: str = "", *tags: str) -> None:
        """
        Dispatches a full notification payload including level, message,
        attachment reference, and destination tags asynchronously.
        """
        if self._closed:
            raise RuntimeError("notification client is closed")

        loop = asyncioGetRunningLoop()
        await loop.run_in_executor(
            _notif_executor,
            self._dispatch_c_call,
            level, message, attachment, *tags
        )

    # -----------------------------------------------------------------------------------------------

    def send_sync(self, message: str, *tags: str) -> None:
        """Synchronous helper dispatching an untyped notification."""
        self.send_with_attachment_sync("", message, "", *tags)

    # -----------------------------------------------------------------------------------------------

    def send_alert_sync(self, level: str, message: str, *tags: str) -> None:
        """Synchronous helper dispatching a categorized alert."""
        self.send_with_attachment_sync(level, message, "", *tags)

    # -----------------------------------------------------------------------------------------------

    def send_with_attachment_sync(self, level: str, message: str, attachment: str = "", *tags: str) -> None:
        """Synchronous helper dispatching a notification over blocking libnotif bridge."""
        if self._closed:
            raise RuntimeError("notification client is closed")

        future = _notif_executor.submit(
            self._dispatch_c_call, level, message, attachment, *tags
        )
        future.result()

    # -----------------------------------------------------------------------------------------------

    def _dispatch_c_call(self, level: str, message: str, attachment: str = "", *tags: str) -> None:
        tags_csv = ",".join(tags)
        target_b = self.target_addr.encode("utf-8")
        level_b = level.encode("utf-8")
        msg_b = message.encode("utf-8")
        att_b = attachment.encode("utf-8")
        tags_b = tags_csv.encode("utf-8")

        rc = self._lib.Notif_SendWithTimeout(
            target_b,
            level_b,
            msg_b,
            att_b,
            tags_b,
            ctypesC_double(self.timeout),
        )

        if rc != 0:
            err_ptr = self._lib.Notif_GetLastError()
            err_str = ""
            if err_ptr:
                err_str = ctypesStringAt(err_ptr).decode("utf-8", errors="replace")
                self._lib.Notif_FreeString(err_ptr)
            self.logger.warning(
                f"Notification dispatch to {self.target_addr} failed (rc={rc}): {err_str}"
            )
            raise RuntimeError(f"SendNotification failed (rc={rc}): {err_str}")

        self.logger.debug(
            f"Notification dispatched successfully to {self.target_addr} (level={level}, tags={tags})"
        )

    # -----------------------------------------------------------------------------------------------

    async def close(self) -> None:
        """Closes active notification client."""
        self.close_sync()

    # -----------------------------------------------------------------------------------------------

    def close_sync(self) -> None:
        """Closes notification client immediately."""
        self._closed = True


# -----------------------------------------------------------------------------------------------
# Functional Factory Aliases for Go Parity
# -----------------------------------------------------------------------------------------------


def new_client(app_config, logger: Optional[Logger] = None) -> NotificationClient:
    """Initializes a NotificationClient dynamically from AppConfig (Go NewClient parity)."""
    return NotificationClient.from_config(app_config, logger)


# -----------------------------------------------------------------------------------------------


def new_client_with_target(target_addr: str, logger: Optional[Logger] = None) -> NotificationClient:
    """Initializes a NotificationClient with an explicit target address (Go NewClientWithTarget parity)."""
    return NotificationClient(target_addr, logger)
