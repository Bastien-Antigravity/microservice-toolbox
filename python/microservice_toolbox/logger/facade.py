#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Python Facade for the Universal Logger (Go) shared library.
Provides integrated configuration management and high-performance logging over CGO.

DATA FLOW:
1. Input: Log messages, severity levels, and structured metadata from application code.
2. Logic: Captures caller frame information and marshals calls into libunilog via ctypes.
3. Output: Structured log entries dispatched to console, file, or log-server via safe-socket.

KEY PARAMETERS:
- app_name: Name of the microservice application.
- logger_profile: Sink configuration profile ("standard", "cloud", etc.).
- log_level: Minimum logging severity threshold.
- config_handle: Pointer handle to the active CGO AppConfig instance.
"""

from asyncio import (
    CancelledError as asyncioCancelledError,
    Queue as asyncioQueue,
    get_event_loop as asyncioGetEventLoop,
    get_running_loop as asyncioGetRunningLoop,
)
from ctypes import c_int as ctypeC_int, string_at as ctypesStringAt
from json import dumps as jsonDumps, loads as jsonLoads
from os.path import basename as osPathBasename
from sys import _getframe as sysGetFrame, stderr as sysStderr
from typing import (
    Any as typeAny,
    Callable as typeCallable,
    Dict as typeDict,
    List as typeList,
    Optional as typeOptional,
    Set as typeSet,
    Tuple as typeTuple,
    Union as typeUnion,
)

from ..utils.lib_loader import LOGGER_CALLBACK_TYPE, load_libunilog
from .logger import Logger
from .models import LogLevel

# -----------------------------------------------------------------------------------------------

lib = load_libunilog()


class ConfigUpdateListener:
    """
    An asynchronous iterator for configuration updates.
    Returned by UniLog.on_config_update() when no callback is provided.
    """

    def __init__(self, parent: 'UniLog') -> None:
        self._parent: 'UniLog' = parent
        self._queue: asyncioQueue[typeDict[str, typeAny]] = asyncioQueue()

        # Capture the active event loop to ensure thread-safe dispatching
        try:
            self._loop = asyncioGetRunningLoop()
        except RuntimeError:
            self._loop = asyncioGetEventLoop()

    def _put(self, data: typeDict[str, typeAny]) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    def __aiter__(self) -> 'ConfigUpdateListener':
        self._parent._async_listeners.add(self)
        return self

    async def __anext__(self) -> typeDict[str, typeAny]:
        try:
            return await self._queue.get()
        except asyncioCancelledError:
            self._parent._async_listeners.discard(self)
            raise

    def __del__(self) -> None:
        if hasattr(self, '_parent'):
            self._parent._async_listeners.discard(self)


class UniLog(Logger):
    """
    UniLog is the primary multi-tenant logger wrapper connecting Python microservices
    directly to the Go unilog subsystem via high-performance ctypes FFI.
    """

    def __init__(self, app_name: str = "python-app", config_profile: str = "standalone",
                 logger_profile: str = "standard", log_level: typeUnion[str, int, LogLevel] = "info",
                 use_local_notifier: bool = False, config_handle: int = 0) -> None:
        if not lib:
            raise RuntimeError("libunilog shared library not found. Please ensure it is built.")

        # Convert string log level to int for Go
        level_val = LogLevel.from_str(log_level) if isinstance(log_level, str) else int(log_level)

        self._handle: int = lib.UniLog_Init(
            app_name.encode('utf-8'),
            config_profile.encode('utf-8'),
            logger_profile.encode('utf-8'),
            ctypeC_int(level_val),
            ctypeC_int(1 if use_local_notifier else 0),
            config_handle
        )
        if not self._handle:
            raise RuntimeError("UniLog_Init returned invalid null handle.")
        self._min_level: int = level_val
        self._callback_ref: typeOptional[typeAny] = None  # Keep reference to avoid GC
        self._sync_subscribers: typeList[typeCallable[[typeDict[str, typeAny]], None]] = []
        self._async_listeners: typeSet[ConfigUpdateListener] = set()
        self._initialized_bridge: bool = False

    ##########################################################################
    # Logging Methods

    def debug(self, msg: str) -> None: self._log(LogLevel.DEBUG, msg)
    def info(self, msg: str) -> None: self._log(LogLevel.INFO, msg)
    def warning(self, msg: str) -> None: self._log(LogLevel.WARNING, msg)
    def error(self, msg: str) -> None: self._log(LogLevel.ERROR, msg)
    def critical(self, msg: str) -> None: self._log(LogLevel.CRITICAL, msg)

    async def async_debug(self, msg: str) -> None: await self._async_log(LogLevel.DEBUG, msg)
    async def async_info(self, msg: str) -> None: await self._async_log(LogLevel.INFO, msg)
    async def async_warning(self, msg: str) -> None: await self._async_log(LogLevel.WARNING, msg)
    async def async_error(self, msg: str) -> None: await self._async_log(LogLevel.ERROR, msg)
    async def async_critical(self, msg: str) -> None: await self._async_log(LogLevel.CRITICAL, msg)

    # Specialized Domain Methods
    def logon(self, msg: str) -> None: self._log(LogLevel.LOGON, msg)
    def logout(self, msg: str) -> None: self._log(LogLevel.LOGOUT, msg)
    def trade(self, msg: str) -> None: self._log(LogLevel.TRADE, msg)
    def schedule(self, msg: str) -> None: self._log(LogLevel.SCHEDULE, msg)
    def report(self, msg: str) -> None: self._log(LogLevel.REPORT, msg)
    def stream(self, msg: str) -> None: self._log(LogLevel.STREAM, msg)

    # Async Specialized Domain Methods
    async def async_logon(self, msg: str) -> None: await self._async_log(LogLevel.LOGON, msg)
    async def async_logout(self, msg: str) -> None: await self._async_log(LogLevel.LOGOUT, msg)
    async def async_trade(self, msg: str) -> None: await self._async_log(LogLevel.TRADE, msg)
    async def async_schedule(self, msg: str) -> None: await self._async_log(LogLevel.SCHEDULE, msg)
    async def async_report(self, msg: str) -> None: await self._async_log(LogLevel.REPORT, msg)
    async def async_stream(self, msg: str) -> None: await self._async_log(LogLevel.STREAM, msg)


    # Log level accessors
    def set_level(self, level: typeUnion[str, int, LogLevel]) -> None:
        """Change the current log level dynamically."""
        if isinstance(level, str):
            level = LogLevel.from_str(level)
        self._min_level = int(level)
        lib.UniLog_SetLevel(self._handle, self._min_level)

    def get_level(self) -> LogLevel:
        """Retrieve the current log level from the Go core."""
        return LogLevel(lib.UniLog_GetLevel(self._handle))

    ##########################################################################
    # Metadata Methods

    def add_metadata(self, key: str, value: str) -> None:
        """Add a single key-value pair to all future logs."""
        lib.UniLog_AddMetadata(self._handle, key.encode('utf-8'), value.encode('utf-8'))

    def set_metadata(self, metadata: typeDict[str, typeAny]) -> None:
        """Replace all existing metadata with the provided dictionary."""
        json_data = jsonDumps(metadata)
        lib.UniLog_SetMetadata(self._handle, json_data.encode('utf-8'))

    ##########################################################################
    # Config Methods

    def get_config(self, section: str, key: str, default: typeOptional[str] = None) -> typeOptional[str]:
        """Retrieve a configuration value from the distributed config service (Zero-Leak FFI)."""
        res_ptr = lib.UniLog_Config_Get(self._handle, section.encode('utf-8'), key.encode('utf-8'))
        if not res_ptr:
            return default
        try:
            return ctypesStringAt(res_ptr).decode('utf-8')
        finally:
            if hasattr(lib, "DistConf_FreeString"):
                lib.DistConf_FreeString(res_ptr)

    def set_config(self, section: str, key: str, value: str) -> None:
        """Update a configuration value in the memory configuration."""
        lib.UniLog_Config_Set(self._handle, section.encode('utf-8'), key.encode('utf-8'), value.encode('utf-8'))

    def _dispatch_update(self, json_data: bytes) -> None:
        """Internal bridge called from Go shared library background thread."""
        try:
            raw_val = json_data.decode('utf-8')
            data = jsonLoads(raw_val)

            # 1. Dispatch to synchronous subscribers
            for cb in self._sync_subscribers:
                try:
                    cb(data)
                except Exception as e:
                    sysStderr.write(f"!!! Sync subscriber error: {e}\n")

            # 2. Dispatch to asynchronous listeners (thread-safe)
            for listener in list(self._async_listeners):
                listener._put(data)
        except Exception as e:
            sysStderr.write(f"!!! _dispatch_update EXCEPTION: {e}\n")

    def on_config_update(self, callback: typeOptional[typeCallable[[typeDict[str, typeAny]], None]] = None) -> typeOptional[ConfigUpdateListener]:
        """
        Registers a mechanism for configuration updates.
        """
        if not self._initialized_bridge:
            self._callback_ref = LOGGER_CALLBACK_TYPE(self._dispatch_update)
            lib.UniLog_OnConfigUpdate(self._handle, self._callback_ref)
            self._initialized_bridge = True

        if callback is not None:
            self._sync_subscribers.append(callback)
            return None

        return ConfigUpdateListener(self)

    def on_notification(self, callback: typeCallable[[typeDict[str, typeAny]], None]) -> None:
        """
        Registers a callback for local notifications.
        """
        def _bridge_cb(json_data: bytes) -> None:
            try:
                data = jsonLoads(json_data.decode('utf-8'))
                callback(data)
            except Exception as e:
                sysStderr.write(f"!!! on_notification EXCEPTION: {e}\n")

        self._notif_callback_ref = LOGGER_CALLBACK_TYPE(_bridge_cb)
        lib.UniLog_RegisterNotifCallback(self._handle, self._notif_callback_ref)

    ##########################################################################
    # Internal sync Logging Method

    def _log(self, level: typeUnion[int, LogLevel], msg: str) -> None:
        if int(level) < self._min_level:
            return
        caller_info = self._get_caller_info(3)
        self._dispatch_log_to_cgo(level, msg, *caller_info)

    ##########################################################################
    # Internal async Logging Method

    async def _async_log(self, level: typeUnion[int, LogLevel], msg: str) -> None:
        if int(level) < self._min_level:
            return
        caller_info = self._get_caller_info(3)
        await asyncioGetRunningLoop().run_in_executor(
            None,
            self._dispatch_log_to_cgo,
            int(level),
            str(msg),
            *caller_info
        )

    def _get_caller_info(self, depth: int) -> typeTuple[str, str, str, str]:
        try:
            frame = sysGetFrame(depth)
            filename = osPathBasename(frame.f_code.co_filename)
            lineno = str(frame.f_lineno)
            function = frame.f_code.co_name
            module = frame.f_globals.get('__name__', 'unknown')
            return filename, lineno, function, module
        except Exception:
            return "unknown_file", "0", "unknown_func", "unknown_mod"

    def _dispatch_log_to_cgo(self, level: typeUnion[int, LogLevel], msg: str, filename: str, lineno: str, function: str, module: str) -> None:
        lib.UniLog_LogWithMetadata(
            self._handle,
            int(level),
            str(msg).encode('utf-8'),
            filename.encode('utf-8'),
            lineno.encode('utf-8'),
            function.encode('utf-8'),
            module.encode('utf-8')
        )

    def close(self) -> None:
        """Manually release the logger session and associated resources."""
        if hasattr(self, '_handle') and self._handle:
            lib.UniLog_Close(self._handle)
            self._handle = None

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> 'UniLog':
        return self

    def __exit__(self, exc_type: typeAny, exc_val: typeAny, exc_tb: typeAny) -> None:
        self.close()

    async def __aenter__(self) -> 'UniLog':
        return self.__enter__()

    async def __aexit__(self, exc_type: typeAny, exc_val: typeAny, exc_tb: typeAny) -> None:
        return self.__exit__(exc_type, exc_val, exc_tb)
