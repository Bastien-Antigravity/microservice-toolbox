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
        from .logger import Logger, LogLevel, UniLog, ensure_safe_logger
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
            from .messaging import JetStreamConfig, NatsConfig, connect
            globals()["NatsConfig"] = NatsConfig
            globals()["JetStreamConfig"] = JetStreamConfig
            globals()["connect"] = connect
        except ImportError:
            globals()["NatsConfig"] = None
            globals()["JetStreamConfig"] = None
            globals()["connect"] = None
        return globals()[name]
    if name in ["NotificationClient", "new_notification_client"]:
        from .notification import NotificationClient, new_client
        globals()["NotificationClient"] = NotificationClient
        globals()["new_notification_client"] = new_client
        return globals()[name]
    if name in ["get_version", "resolve_version"]:
        from .version import get_version, resolve_version
        globals()["get_version"] = get_version
        globals()["resolve_version"] = resolve_version
        return globals()[name]
    if name in [
        "publish",
        "publish_with_lifecycle",
        "publish_sync",
        "build_spec_from_config",
        "publish_service_spec",
        "ServiceSpec",
        "ProtocolSpec",
        "Publish",
        "PublishWithLifecycle",
        "PublishSync",
        "BuildSpecFromConfig",
    ]:
        from .spec import (
            publish,
            publish_with_lifecycle,
            publish_sync,
            build_spec_from_config,
            publish_service_spec,
            ServiceSpec,
            ProtocolSpec,
            Publish,
            PublishWithLifecycle,
            PublishSync,
            BuildSpecFromConfig,
        )
        globals()["publish"] = publish
        globals()["publish_with_lifecycle"] = publish_with_lifecycle
        globals()["publish_sync"] = publish_sync
        globals()["build_spec_from_config"] = build_spec_from_config
        globals()["publish_service_spec"] = publish_service_spec
        globals()["ServiceSpec"] = ServiceSpec
        globals()["ProtocolSpec"] = ProtocolSpec
        globals()["Publish"] = Publish
        globals()["PublishWithLifecycle"] = PublishWithLifecycle
        globals()["PublishSync"] = PublishSync
        globals()["BuildSpecFromConfig"] = BuildSpecFromConfig
        return globals()[name]
        return globals()[name]
    if name in [
        "ContractPeer",
        "ContractOperation",
        "ExchangeContract",
        "build_contracts_envelope",
        "extract_fastapi_operations",
        "extract_proto_operations",
    ]:
        from .contracts import (
            ContractPeer,
            ContractOperation,
            ExchangeContract,
            build_contracts_envelope,
            extract_fastapi_operations,
            extract_proto_operations,
        )
        globals()["ContractPeer"] = ContractPeer
        globals()["ContractOperation"] = ContractOperation
        globals()["ExchangeContract"] = ExchangeContract
        globals()["build_contracts_envelope"] = build_contracts_envelope
        globals()["extract_fastapi_operations"] = extract_fastapi_operations
        globals()["extract_proto_operations"] = extract_proto_operations
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "load_config",
    "load_config_with_logger",
    "ServiceSpec",
    "ProtocolSpec",
    "publish",
    "publish_with_lifecycle",
    "publish_sync",
    "build_spec_from_config",
    "Publish",
    "PublishWithLifecycle",
    "PublishSync",
    "BuildSpecFromConfig",
    "publish_service_spec",
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
    "NotificationClient",
    "new_notification_client",
    "get_version",
    "resolve_version",
]

