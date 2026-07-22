#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Python Facade for the Universal Logger (Go) shared library.
Provides integrated configuration management and high-performance logging.
"""

from os.path import basename as osPathBasename
from ctypes import c_int as ctypeC_int
from sys import _getframe as sysGetFrame
from json import loads as jsonLoads
from asyncio import (
    get_running_loop as asyncioGetRunningLoop,
    get_event_loop as asyncioGetEventLoop,
    Queue as asyncioQueue,
    CancelledError as asyncioCancelledError
)
import json
from typing import Union, Dict, List, Callable, Optional, Set, Any, Tuple

from .models import LogLevel
from .logger import Logger
from .lib_loader import lib, CALLBACK_TYPE


class ConfigUpdateListener:
    """
    An asynchronous iterator for configuration updates.
    Returned by UniLog.on_config_update() when no callback is provided.
    """

    def __init__(self, parent: 'UniLog') -> None:
        self._parent: 'UniLog' = parent
        self._queue: asyncioQueue[Dict[str, Any]] = asyncioQueue()
        
        # Capture the active event loop to ensure thread-safe dispatching
        try:
            self._loop = asyncioGetRunningLoop()
        except RuntimeError:
            self._loop = asyncioGetEventLoop()
        
    def _put(self, data: Dict[str, Any]) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    def __aiter__(self) -> 'ConfigUpdateListener':
        self._parent._async_listeners.add(self)
        return self

    async def __anext__(self) -> Dict[str, Any]:
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
                 logger_profile: str = "standard", log_level: Union[str, int, LogLevel] = "info", 
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
        self._callback_ref: Optional[Any] = None  # Keep reference to avoid GC
        self._sync_subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._async_listeners: Set[ConfigUpdateListener] = set()
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
    def set_level(self, level: Union[str, int, LogLevel]) -> None:
        """Change the current log level dynamically."""
        if isinstance(level, str):
            level = LogLevel.from_str(level)
        lib.UniLog_SetLevel(self._handle, int(level))
        
    def get_level(self) -> LogLevel:
        """Retrieve the current log level from the Go core."""
        return LogLevel(lib.UniLog_GetLevel(self._handle))

    ##########################################################################
    # Metadata Methods
    
    def add_metadata(self, key: str, value: str) -> None:
        """Add a single key-value pair to all future logs."""
        lib.UniLog_AddMetadata(self._handle, key.encode('utf-8'), value.encode('utf-8'))

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Replace all existing metadata with the provided dictionary."""
        json_data = json.dumps(metadata)
        lib.UniLog_SetMetadata(self._handle, json_data.encode('utf-8'))

    ##########################################################################
    # Config Methods
    
    def get_config(self, section: str, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a configuration value from the distributed config service (Zero-Leak FFI)."""
        res_ptr = lib.UniLog_Config_Get(self._handle, section.encode('utf-8'), key.encode('utf-8'))
        if not res_ptr:
            return default
        try:
            from ctypes import string_at
            return string_at(res_ptr).decode('utf-8')
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
                    print(f"!!! Sync subscriber error: {e}")
            
            # 2. Dispatch to asynchronous listeners (thread-safe)
            for listener in list(self._async_listeners):
                listener._put(data)
        except Exception as e:
            print(f"!!! _dispatch_update EXCEPTION: {e}")

    def on_config_update(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Optional[ConfigUpdateListener]:
        """
        Registers a mechanism for configuration updates.
        """
        if not self._initialized_bridge:
            self._callback_ref = CALLBACK_TYPE(self._dispatch_update)
            lib.UniLog_OnConfigUpdate(self._handle, self._callback_ref)
            self._initialized_bridge = True

        if callback is not None:
            self._sync_subscribers.append(callback)
            return None
        
        return ConfigUpdateListener(self)

    def on_notification(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Registers a callback for local notifications.
        """
        def _bridge_cb(json_data: bytes) -> None:
            try:
                data = jsonLoads(json_data.decode('utf-8'))
                callback(data)
            except Exception as e:
                print(f"!!! on_notification EXCEPTION: {e}")

        self._notif_callback_ref = CALLBACK_TYPE(_bridge_cb)
        lib.UniLog_RegisterNotifCallback(self._handle, self._notif_callback_ref)

    ##########################################################################
    # Internal sync Logging Method
    
    def _log(self, level: Union[int, LogLevel], msg: str) -> None:
        caller_info = self._get_caller_info(3)
        self._dispatch_log_to_cgo(level, msg, *caller_info)

    ##########################################################################
    # Internal async Logging Method
    
    async def _async_log(self, level: Union[int, LogLevel], msg: str) -> None:
        caller_info = self._get_caller_info(3)
        await asyncioGetRunningLoop().run_in_executor(
            None, 
            self._dispatch_log_to_cgo, 
            int(level), 
            str(msg), 
            *caller_info
        )

    def _get_caller_info(self, depth: int) -> Tuple[str, str, str, str]:
        try:
            frame = sysGetFrame(depth)
            filename = osPathBasename(frame.f_code.co_filename)
            lineno = str(frame.f_lineno)
            function = frame.f_code.co_name
            module = frame.f_globals.get('__name__', 'unknown')
            return filename, lineno, function, module
        except Exception:
            return "unknown_file", "0", "unknown_func", "unknown_mod"

    def _dispatch_log_to_cgo(self, level: Union[int, LogLevel], msg: str, filename: str, lineno: str, function: str, module: str) -> None:
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

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> 'UniLog':
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.__exit__(exc_type, exc_val, exc_tb)
