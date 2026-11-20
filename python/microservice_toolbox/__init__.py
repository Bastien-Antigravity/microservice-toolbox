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
    if name in ["LifecycleManager", "new_manager", "new_manager_with_logger"]:
        from .lifecycle.manager import LifecycleManager, new_manager, new_manager_with_logger
        globals()["LifecycleManager"] = LifecycleManager
        globals()["new_manager"] = new_manager
        globals()["new_manager_with_logger"] = new_manager_with_logger
        return globals()[name]
    if name in ["Resolver", "new_resolver"]:
        from .connectivity.resolver import Resolver, new_resolver
        globals()["Resolver"] = Resolver
        globals()["new_resolver"] = new_resolver
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
    if name in ["get_version", "resolve_version", "set_version", "reset_version"]:
        from .version import (
            get_version,
            reset_version,
            resolve_version,
            set_version,
        )
        globals()["get_version"] = get_version
        globals()["resolve_version"] = resolve_version
        globals()["set_version"] = set_version
        globals()["reset_version"] = reset_version
        return globals()[name]
    if name in [
        "publish",
        "publish_with_lifecycle",
        "publish_sync",
        "build_spec_from_config",
        "publish_service_spec",
        "ServiceSpec",
        "ProtocolSpec",
        "DependencySpec",
        "HealthSpec",
        "CanvasSpec",
        "Publish",
        "PublishWithLifecycle",
        "PublishSync",
        "BuildSpecFromConfig",
        "resolve_mfe_url",
        "ResolveMFEURL",
    ]:
        from .spec import (
            BuildSpecFromConfig,
            CanvasSpec,
            DependencySpec,
            HealthSpec,
            ProtocolSpec,
            Publish,
            PublishSync,
            PublishWithLifecycle,
            ResolveMFEURL,
            ServiceSpec,
            build_spec_from_config,
            publish,
            publish_service_spec,
            publish_sync,
            publish_with_lifecycle,
            resolve_mfe_url,
        )
        globals()["publish"] = publish
        globals()["publish_with_lifecycle"] = publish_with_lifecycle
        globals()["publish_sync"] = publish_sync
        globals()["build_spec_from_config"] = build_spec_from_config
        globals()["publish_service_spec"] = publish_service_spec
        globals()["ServiceSpec"] = ServiceSpec
        globals()["ProtocolSpec"] = ProtocolSpec
        globals()["DependencySpec"] = DependencySpec
        globals()["HealthSpec"] = HealthSpec
        globals()["CanvasSpec"] = CanvasSpec
        globals()["Publish"] = Publish
        globals()["PublishWithLifecycle"] = PublishWithLifecycle
        globals()["PublishSync"] = PublishSync
        globals()["BuildSpecFromConfig"] = BuildSpecFromConfig
        globals()["resolve_mfe_url"] = resolve_mfe_url
        globals()["ResolveMFEURL"] = ResolveMFEURL
        return globals()[name]
    if name in [
        "ContractPeer",
        "ContractOperation",
        "ExchangeContract",
        "ContractsEnvelope",
        "new_contracts_envelope",
        "build_contracts_envelope",
        "display_address",
        "resolve_contract_port",
        "read_schema_file",
        "extract_fastapi_operations",
        "extract_proto_operations",
        "extract_capnp_operations",
    ]:
        from .contracts import (
            ContractOperation,
            ContractPeer,
            ContractsEnvelope,
            ExchangeContract,
            build_contracts_envelope,
            display_address,
            extract_capnp_operations,
            extract_fastapi_operations,
            extract_proto_operations,
            new_contracts_envelope,
            read_schema_file,
            resolve_contract_port,
        )
        globals()["ContractPeer"] = ContractPeer
        globals()["ContractOperation"] = ContractOperation
        globals()["ExchangeContract"] = ExchangeContract
        globals()["ContractsEnvelope"] = ContractsEnvelope
        globals()["new_contracts_envelope"] = new_contracts_envelope
        globals()["build_contracts_envelope"] = build_contracts_envelope
        globals()["display_address"] = display_address
        globals()["resolve_contract_port"] = resolve_contract_port
        globals()["read_schema_file"] = read_schema_file
        globals()["extract_fastapi_operations"] = extract_fastapi_operations
        globals()["extract_proto_operations"] = extract_proto_operations
        globals()["extract_capnp_operations"] = extract_capnp_operations
        return globals()[name]
    if name in [
        "MarketEvent",
        "MarketEventType",
        "Aggressor",
        "Trade",
        "Quote",
        "OrderBookLevel",
        "OrderBook",
        "OHLCV",
        "Signal",
        "SignalType",
        "serialize",
        "deserialize",
        "wrap_market_event",
        "system_timestamp",
    ]:
        from .business import (
            OHLCV,
            Aggressor,
            MarketEvent,
            MarketEventType,
            OrderBook,
            OrderBookLevel,
            Quote,
            Signal,
            SignalType,
            Trade,
            deserialize,
            serialize,
            system_timestamp,
            wrap_market_event,
        )
        globals()["MarketEvent"] = MarketEvent
        globals()["MarketEventType"] = MarketEventType
        globals()["Aggressor"] = Aggressor
        globals()["Trade"] = Trade
        globals()["Quote"] = Quote
        globals()["OrderBookLevel"] = OrderBookLevel
        globals()["OrderBook"] = OrderBook
        globals()["OHLCV"] = OHLCV
        globals()["Signal"] = Signal
        globals()["SignalType"] = SignalType
        globals()["serialize"] = serialize
        globals()["deserialize"] = deserialize
        globals()["wrap_market_event"] = wrap_market_event
        globals()["system_timestamp"] = system_timestamp
        return globals()[name]
    if name == "wiretap":
        import importlib
        mod = importlib.import_module(".wiretap", __name__)
        globals()["wiretap"] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "load_config",
    "load_config_with_logger",
    "Resolver",
    "new_resolver",
    "LifecycleManager",
    "new_manager",
    "new_manager_with_logger",
    "ServiceSpec",
    "ProtocolSpec",
    "DependencySpec",
    "HealthSpec",
    "CanvasSpec",
    "publish",
    "publish_with_lifecycle",
    "publish_sync",
    "build_spec_from_config",
    "Publish",
    "PublishWithLifecycle",
    "PublishSync",
    "BuildSpecFromConfig",
    "publish_service_spec",
    "ContractPeer",
    "ContractOperation",
    "ExchangeContract",
    "ContractsEnvelope",
    "new_contracts_envelope",
    "build_contracts_envelope",
    "display_address",
    "resolve_contract_port",
    "read_schema_file",
    "extract_fastapi_operations",
    "extract_proto_operations",
    "extract_capnp_operations",
    "MarketEvent",
    "MarketEventType",
    "Aggressor",
    "Trade",
    "Quote",
    "OrderBookLevel",
    "OrderBook",
    "OHLCV",
    "Signal",
    "SignalType",
    "serialize",
    "deserialize",
    "wrap_market_event",
    "system_timestamp",
    "wiretap",
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
    "set_version",
    "reset_version",
]
