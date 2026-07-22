#!/usr/bin/env python
# coding:utf-8

"""
Microservice Toolbox: A cross-language toolkit for reliable microservice development.
"""

def __getattr__(name):
    if name in ["load_config", "load_config_with_logger"]:
        from .config.loader import load_config, load_config_with_logger
        globals()["load_config"] = load_config
        globals()["load_config_with_logger"] = load_config_with_logger
        return globals()[name]
    if name in ["new_manager", "new_manager_with_logger"]:
        from .lifecycle.manager import new_manager, new_manager_with_logger
        globals()["new_manager"] = new_manager
        globals()["new_manager_with_logger"] = new_manager_with_logger
        return globals()[name]
    if name in ["UniLog", "LogLevel", "Logger", "ensure_safe_logger"]:
        from .logger import UniLog, LogLevel, Logger, ensure_safe_logger
        globals()["UniLog"] = UniLog
        globals()["LogLevel"] = LogLevel
        globals()["Logger"] = Logger
        globals()["ensure_safe_logger"] = ensure_safe_logger
        return globals()[name]
    if name == "init_microservice":
        from .utils.init import init_microservice
        globals()["init_microservice"] = init_microservice
        return init_microservice
    if name in ["NatsConfig", "JetStreamConfig", "connect"]:
        try:
            from .messaging import NatsConfig, JetStreamConfig, connect
            globals()["NatsConfig"] = NatsConfig
            globals()["JetStreamConfig"] = JetStreamConfig
            globals()["connect"] = connect
        except ImportError:
            globals()["NatsConfig"] = None
            globals()["JetStreamConfig"] = None
            globals()["connect"] = None
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "load_config",
    "load_config_with_logger",
    "new_manager",
    "new_manager_with_logger",
    "NatsConfig",
    "JetStreamConfig",
    "connect",
    "UniLog",
    "LogLevel",
    "Logger",
    "ensure_safe_logger",
    "init_microservice",
]

