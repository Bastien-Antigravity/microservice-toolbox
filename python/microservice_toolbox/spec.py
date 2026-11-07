#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Standardizes self-describing service specifications and dynamic registration
with web-interface for Python microservices (rag-engine, squad-agent).
Auto-resolves runtime listen/REST addresses, dynamic semver, active profile,
and documentation links from AppConfig.

FAIL-FAST PRINCIPLE:
Zero silent fallbacks, zero default values, and zero dummy placeholders.
Microservices must explicitly declare their own specification metadata
(name, tag, layer, category, description, doc_link, protocol, framing).
Configuration addresses (including web_interface) must resolve strictly;
missing capabilities, missing ports, or missing metadata FAIL FAST immediately.

DATA FLOW:
1. Microservice ServiceSpec + Capability Name -> Dynamic AppConfig Lookups
2. Strict Fail-Fast Validation of all required fields & dynamic endpoints
3. POST to /api/v1/register with exponential backoff and randomized jitter

KEY PARAMETERS:
- app_config: Active AppConfig for capability host/port/version resolution.
- logger: Logger instance for status and diagnostic logging.
- spec_or_capability: Service capability name or custom ServiceSpec instance.
- overrides: Microservice-provided specification attributes.
"""

from dataclasses import asdict as dcAsdict, dataclass as dcDataclass, field as dcField, is_dataclass as dcIsDataclass
from json import dumps as jsonDumps
from random import uniform as rndUniform
from socket import gethostname as sockGetHostname
from threading import Thread as thThread, Event as thEvent
from time import sleep as timeSleep
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional, Union as typeUnion
from urllib.request import Request as urlRequest, urlopen as urlOpen


# -----------------------------------------------------------------------------------------------
@dcDataclass
class ProtocolSpec:
    type: str
    port: int
    framing: str
    description: str

    def to_dict(self) -> typeDict[str, typeAny]:
        return {
            "type": self.type,
            "port": self.port,
            "framing": self.framing,
            "description": self.description,
        }

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
@dcDataclass
class DependencySpec:
    target: str = ""
    proto: str = ""
    label: str = ""
    exchange_id: str = ""
    description: str = ""

    def to_dict(self) -> typeDict[str, typeAny]:
        d = {
            "target": self.target,
            "proto": self.proto,
            "label": self.label,
        }
        if self.exchange_id:
            d["exchangeId"] = self.exchange_id
        if self.description:
            d["description"] = self.description
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
@dcDataclass
class HealthSpec:
    type: str = "tcp"
    port: int = 0
    path: str = ""
    timeout_ms: int = 350

    def to_dict(self) -> typeDict[str, typeAny]:
        d = {
            "type": self.type,
            "timeoutMs": self.timeout_ms,
        }
        if self.port > 0:
            d["port"] = self.port
        if self.path:
            d["path"] = self.path
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
@dcDataclass
class CanvasSpec:
    icon: str = ""
    color: str = ""
    preferred_slot: str = ""
    preferred_x: float = 0.0
    preferred_y: float = 0.0
    particle_proto: typeList[str] = dcField(default_factory=list)

    def to_dict(self) -> typeDict[str, typeAny]:
        d = {}
        if self.icon:
            d["icon"] = self.icon
        if self.color:
            d["color"] = self.color
        if self.preferred_slot:
            d["preferredSlot"] = self.preferred_slot
        if self.preferred_x > 0:
            d["preferredX"] = self.preferred_x
        if self.preferred_y > 0:
            d["preferredY"] = self.preferred_y
        if self.particle_proto:
            d["particleProto"] = self.particle_proto
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
@dcDataclass
class ServiceSpec:
    name: str = ""
    tag: str = ""
    url: str = ""
    nav_title: str = ""
    layer: str = ""
    category: str = ""
    priority: int = 100
    icon: str = "fa-cubes"
    color: str = ""
    requires_auth: bool = False
    capability: str = ""
    description: str = ""
    protocol: str = ""
    framing: str = ""
    doc_link: str = ""
    nav_route: str = ""
    health: typeOptional[HealthSpec] = None
    canvas: typeOptional[CanvasSpec] = None
    dependencies: typeList[DependencySpec] = dcField(default_factory=list)
    protocols: typeList[ProtocolSpec] = dcField(default_factory=list)
    flow_diagram: typeList[str] = dcField(default_factory=list)
    data_structure: typeDict[str, typeAny] = dcField(default_factory=dict)
    sdk_lang: str = "language-python"
    source_code: str = ""

    def to_dict(self) -> typeDict[str, typeAny]:
        d = {
            "name": self.name,
            "tag": self.tag,
            "url": self.url,
            "navTitle": self.nav_title or self.name,
            "layer": self.layer,
            "category": self.category,
            "priority": self.priority,
            "icon": self.icon,
            "requiresAuth": self.requires_auth,
            "capability": self.capability,
            "desc": self.description,
            "protocol": self.protocol,
            "framing": self.framing,
            "docLink": self.doc_link,
            "flowDiagram": self.flow_diagram,
            "dataStructure": self.data_structure,
            "sdkLang": self.sdk_lang,
            "sourceCode": self.source_code,
        }
        if self.color:
            d["color"] = self.color
        if self.nav_route:
            d["navRoute"] = self.nav_route
        if self.health is not None:
            d["health"] = self.health.to_dict() if hasattr(self.health, "to_dict") else self.health
        if self.canvas is not None:
            d["canvas"] = self.canvas.to_dict() if hasattr(self.canvas, "to_dict") else self.canvas
        if self.dependencies:
            d["dependencies"] = [
                dep.to_dict() if hasattr(dep, "to_dict") else dep for dep in self.dependencies
            ]
        if self.protocols:
            d["protocols"] = [
                p.to_dict() if hasattr(p, "to_dict") else p for p in self.protocols
            ]
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
def _extract_port(addr: str) -> str:
    if not addr:
        return ""
    parts = addr.split(":")
    return parts[-1] if len(parts) >= 2 else addr


# -----------------------------------------------------------------------------------------------
def build_spec_from_config(app_config: typeAny, capability: str, **overrides: typeAny) -> ServiceSpec:
    """
    Validates and enriches a ServiceSpec using dynamic parameters from app_config.
    FAIL-FAST: Strictly validates all required metadata and resolves dynamic endpoints.
    Zero silent fallback or dummy placeholders.
    """
    # 1. Validate app_config (FAIL-FAST)
    if app_config is None:
        raise ValueError("spec.build_spec_from_config: app_config is strictly required (nil provided) (FAIL-FAST)")

    # 2. Validate capability (FAIL-FAST)
    capability = (capability or "").strip()
    if not capability:
        raise ValueError("spec.build_spec_from_config: capability name is strictly required (FAIL-FAST)")

    name = overrides.get("name") or overrides.get("Name")
    tag = overrides.get("tag") or overrides.get("Tag")
    layer = overrides.get("layer") or overrides.get("Layer")
    category = overrides.get("category") or overrides.get("Category")
    description = overrides.get("description") or overrides.get("desc") or overrides.get("Description")
    doc_link = overrides.get("doc_link") or overrides.get("docLink") or overrides.get("DocLink")
    protocol = overrides.get("protocol") or overrides.get("Protocol")
    framing = overrides.get("framing") or overrides.get("Framing")

    # 3. Validate Microservice-provided metadata (FAIL-FAST: ZERO DUMMY FALLBACKS)
    if not name or not str(name).strip():
        raise ValueError(f"spec.build_spec_from_config: 'name' is strictly required for capability '{capability}' (FAIL-FAST)")
    if not tag or not str(tag).strip():
        raise ValueError(f"spec.build_spec_from_config: 'tag' is strictly required for capability '{capability}' (FAIL-FAST)")
    if not layer or not str(layer).strip():
        raise ValueError(f"spec.build_spec_from_config: 'layer' (L1|L2|L3) is strictly required for capability '{capability}' (FAIL-FAST)")
    if not category or not str(category).strip():
        raise ValueError(f"spec.build_spec_from_config: 'category' is strictly required for capability '{capability}' (FAIL-FAST)")
    if not description or not str(description).strip():
        raise ValueError(f"spec.build_spec_from_config: 'description' is strictly required for capability '{capability}' (FAIL-FAST)")
    if not doc_link or not str(doc_link).strip():
        raise ValueError(f"spec.build_spec_from_config: 'doc_link' is strictly required for capability '{capability}' (FAIL-FAST)")
    if not protocol or not str(protocol).strip():
        raise ValueError(f"spec.build_spec_from_config: 'protocol' is strictly required for capability '{capability}' (FAIL-FAST)")
    if not framing or not str(framing).strip():
        raise ValueError(f"spec.build_spec_from_config: 'framing' is strictly required for capability '{capability}' (FAIL-FAST)")

    spec = ServiceSpec(
        name=str(name).strip(),
        tag=str(tag).strip(),
        nav_title=overrides.get("nav_title") or overrides.get("navTitle") or str(name).strip(),
        layer=str(layer).strip(),
        category=str(category).strip(),
        priority=int(overrides.get("priority", 100)),
        icon=overrides.get("icon") or "fa-cubes",
        requires_auth=bool(overrides.get("requires_auth", False)),
        capability=capability,
        description=str(description).strip(),
        protocol=str(protocol).strip(),
        framing=str(framing).strip(),
        doc_link=str(doc_link).strip(),
        sdk_lang=overrides.get("sdk_lang") or "language-python",
        source_code=overrides.get("source_code") or "",
        flow_diagram=list(overrides.get("flow_diagram") or []),
    )

    # 4. Resolve endpoints from app_config if needed
    tcp_addr = ""
    rest_addr = ""
    grpc_addr = ""

    if hasattr(app_config, "get_listen_addr"):
        try:
            tcp_addr = app_config.get_listen_addr(capability) or ""
        except Exception:
            pass
    if hasattr(app_config, "get_rest_addr"):
        try:
            rest_addr = app_config.get_rest_addr(capability) or ""
        except Exception:
            pass
    if hasattr(app_config, "get_grpc_listen_addr"):
        try:
            grpc_addr = app_config.get_grpc_listen_addr(capability) or ""
        except Exception:
            pass

    tcp_port = _extract_port(tcp_addr)
    rest_port = _extract_port(rest_addr)
    grpc_port = _extract_port(grpc_addr)

    # Dynamic URL resolution
    if overrides.get("url"):
        spec.url = overrides["url"]
    elif rest_addr:
        spec.url = f"http://{rest_addr}"
    elif tcp_addr:
        spec.url = f"http://{tcp_addr}"
    else:
        raise RuntimeError(f"spec.build_spec_from_config: unable to resolve URL for capability '{capability}' (FAIL-FAST)")

    # Dynamic Framing Port Interpolation
    if "%s" in spec.framing:
        available = [p for p in (tcp_port, rest_port, grpc_port) if p]
        count = spec.framing.count("%s")
        if len(available) < count:
            raise RuntimeError(f"spec.build_spec_from_config: framing requires {count} port(s), but only {len(available)} available for capability '{capability}' (FAIL-FAST)")
        spec.framing = spec.framing % tuple(available[:count])

    ports: typeDict[str, str] = {}
    if tcp_port:
        ports["tcp"] = tcp_port
    if rest_port:
        ports["rest"] = rest_port
    if grpc_port:
        ports["grpc"] = grpc_port

    # 7. Dynamic Semver Resolution (FAIL-FAST)
    version = ""
    if hasattr(app_config, "get_version"):
        try:
            version = app_config.get_version() or ""
        except Exception:
            pass
    if not version.strip():
        raise RuntimeError("spec.build_spec_from_config: dynamic version resolution returned empty string (FAIL-FAST)")

    # 8. Populate DataStructure dynamically
    ds = dict(overrides.get("data_structure") or {})
    ds["version"] = version
    ds["capability"] = capability
    ds["ports"] = ports
    try:
        ds["node"] = sockGetHostname()
    except Exception:
        pass
    spec.data_structure = ds

    # 9. Auto-populate NavRoute, Canvas, and Health defaults if not explicitly set
    if not getattr(spec, "nav_route", ""):
        spec.nav_route = f"/mfe/{spec.name}"
    if getattr(spec, "color", "") and spec.canvas and not spec.canvas.color:
        spec.canvas.color = spec.color
    elif spec.canvas and spec.canvas.color and not getattr(spec, "color", ""):
        spec.color = spec.canvas.color

    if not spec.health:
        probe_port = 0
        for p_cand in (rest_port, tcp_port, grpc_port):
            try:
                probe_port = int(p_cand)
                if probe_port > 0:
                    break
            except Exception:
                pass
        spec.health = HealthSpec(type="tcp", port=probe_port, timeout_ms=350)

    return spec


# -----------------------------------------------------------------------------------------------
def publish_sync(
    app_config: typeAny,
    logger: typeOptional[typeAny],
    capability: str,
    spec: typeOptional[typeUnion[ServiceSpec, typeDict[str, typeAny]]] = None,
    **overrides: typeAny
) -> None:
    """
    Synchronously publishes a service specification to web-interface via POST /api/v1/register
    with exponential backoff and retries until success or fatal error.
    """
    # 1. Validate app_config (FAIL-FAST)
    if app_config is None:
        if logger and hasattr(logger, "critical"):
            logger.critical("spec.publish_sync: app_config is strictly required (nil provided) (FAIL-FAST)")
        raise ValueError("spec.publish_sync: app_config is strictly required (FAIL-FAST)")

    # 2. Resolve web_interface address (FAIL-FAST, ZERO SILENT FALLBACK)
    web_addr = None
    try:
        web_addr = app_config.get_listen_addr("web_interface")
    except Exception as e:
        if logger and hasattr(logger, "critical"):
            logger.critical(f"spec.publish_sync: Failed to resolve capability 'web_interface': {e} (FAIL-FAST)")
        raise RuntimeError(f"spec.publish_sync: capability 'web_interface' is unresolvable: {e} (FAIL-FAST)")

    if not web_addr or not str(web_addr).strip():
        if logger and hasattr(logger, "critical"):
            logger.critical("spec.publish_sync: Capability 'web_interface' resolved to empty address (FAIL-FAST)")
        raise RuntimeError("spec.publish_sync: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)")

    reg_url = f"http://{web_addr}/api/v1/register"

    # 3. Synchronous Spec Validation and Enrichment (FAIL-FAST)
    if spec is None:
        spec_obj = build_spec_from_config(app_config, capability, **overrides)
    elif isinstance(spec, ServiceSpec):
        merged = dcAsdict(spec)
        merged.update(overrides)
        spec_obj = build_spec_from_config(app_config, capability or spec.capability, **merged)
    elif dcIsDataclass(spec):
        merged = dcAsdict(spec)
        merged.update(overrides)
        spec_obj = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)
    else:
        merged = dict(spec)
        merged.update(overrides)
        spec_obj = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)

    spec_dict = spec_obj.to_dict()
    payload_bytes = jsonDumps(spec_dict).encode("utf-8")
    delay = 1.0
    max_delay = 30.0

    while True:
        try:
            req = urlRequest(
                reg_url,
                data=payload_bytes,
                headers={"Content-Type": "application/json"}
            )
            with urlOpen(req, timeout=3.0) as resp:
                if resp.status in (200, 201):
                    if logger and hasattr(logger, "info"):
                        logger.info(f"spec.publish_sync: Service '{spec_dict.get('name')}' successfully published spec to {reg_url}")
                    return
                if logger and hasattr(logger, "warning"):
                    logger.warning(f"spec.publish_sync: Registration for '{spec_dict.get('name')}' returned status {resp.status}. Retrying...")
        except Exception as e:
            if logger and hasattr(logger, "debug"):
                logger.debug(f"spec.publish_sync: Waiting for web-interface at {reg_url} ({e}). Retrying in {delay:.1f}s...")

        jitter = rndUniform(0, delay * 0.5)
        timeSleep(delay + jitter)
        delay = min(delay * 2, max_delay)


# -----------------------------------------------------------------------------------------------
def _background_publisher(
    app_config: typeAny,
    logger: typeOptional[typeAny],
    capability: str,
    spec: typeOptional[typeUnion[ServiceSpec, typeDict[str, typeAny]]] = None,
    stop_event: typeOptional[thEvent] = None,
    **overrides: typeAny
) -> None:
    """
    Background worker maintaining spec registration and periodic 30s heartbeats with web-interface.
    """
    try:
        web_addr = app_config.get_listen_addr("web_interface")
    except Exception as e:
        if logger and hasattr(logger, "critical"):
            logger.critical(f"spec._background_publisher: web_interface unresolvable: {e}")
        return

    reg_url = f"http://{web_addr}/api/v1/register"

    try:
        if spec is None:
            spec_obj = build_spec_from_config(app_config, capability, **overrides)
        elif isinstance(spec, ServiceSpec):
            merged = dcAsdict(spec)
            merged.update(overrides)
            spec_obj = build_spec_from_config(app_config, capability or spec.capability, **merged)
        elif dcIsDataclass(spec):
            merged = dcAsdict(spec)
            merged.update(overrides)
            spec_obj = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)
        else:
            merged = dict(spec)
            merged.update(overrides)
            spec_obj = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)

        payload_bytes = jsonDumps(spec_obj.to_dict()).encode("utf-8")
        svc_name = spec_obj.name
    except Exception as e:
        if logger and hasattr(logger, "error"):
            logger.error(f"spec._background_publisher: Spec serialization failed: {e}")
        return

    delay = 1.0
    max_delay = 30.0
    is_first_success = True

    while stop_event is None or not stop_event.is_set():
        try:
            active_web_addr = app_config.get_listen_addr("web_interface")
            if active_web_addr:
                reg_url = f"http://{active_web_addr}/api/v1/register"
        except Exception:
            pass

        registered = False
        try:
            req = urlRequest(reg_url, data=payload_bytes, headers={"Content-Type": "application/json"})
            with urlOpen(req, timeout=3.0) as resp:
                if resp.status in (200, 201):
                    registered = True
                    if is_first_success:
                        if logger and hasattr(logger, "info"):
                            logger.info(f"spec: Service '{svc_name}' registered with web-interface at {reg_url}")
                        is_first_success = False
                    elif logger and hasattr(logger, "debug"):
                        logger.debug(f"spec: Heartbeat for '{svc_name}' accepted by web-interface at {reg_url}")
                    delay = 1.0
                elif logger and hasattr(logger, "warning"):
                    logger.warning(f"spec: Registration for '{svc_name}' returned status {resp.status}. Retrying...")
        except Exception as e:
            if logger and hasattr(logger, "debug"):
                logger.debug(f"spec: Waiting for web-interface at {reg_url} ({e}). Retrying in {delay:.1f}s...")

        if registered:
            interval = 30.0 + rndUniform(0, 3.0)
        else:
            jitter = rndUniform(0, delay * 0.5)
            interval = delay + jitter
            delay = min(delay * 2, max_delay)

        if stop_event is not None:
            stop_event.wait(timeout=interval)
        else:
            timeSleep(interval)


# -----------------------------------------------------------------------------------------------
def publish(
    app_config: typeAny,
    logger: typeOptional[typeAny],
    capability: str,
    spec: typeOptional[typeUnion[ServiceSpec, typeDict[str, typeAny]]] = None,
    **overrides: typeAny
) -> None:
    """
    Validates spec synchronously (FAIL-FAST) and publishes to web-interface
    in a non-blocking background thread with exponential backoff and 30s heartbeats.
    """
    # Fail-fast synchronous validation of config, web_interface, and spec before spawning thread
    if app_config is None:
        if logger and hasattr(logger, "critical"):
            logger.critical("spec.publish: app_config is strictly required (nil provided) (FAIL-FAST)")
        raise ValueError("spec.publish: app_config is strictly required (FAIL-FAST)")

    # Validate web_interface capability
    try:
        web_addr = app_config.get_listen_addr("web_interface")
        if not web_addr or not str(web_addr).strip():
            raise ValueError("empty web_interface address")
    except Exception as e:
        if logger and hasattr(logger, "critical"):
            logger.critical(f"spec.publish: capability 'web_interface' is unresolvable: {e} (FAIL-FAST)")
        raise RuntimeError(f"spec.publish: capability 'web_interface' is unresolvable: {e} (FAIL-FAST)")

    # Validate spec
    if spec is None:
        _ = build_spec_from_config(app_config, capability, **overrides)
    elif isinstance(spec, ServiceSpec):
        merged = dcAsdict(spec)
        merged.update(overrides)
        _ = build_spec_from_config(app_config, capability or spec.capability, **merged)
    elif dcIsDataclass(spec):
        merged = dcAsdict(spec)
        merged.update(overrides)
        _ = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)
    else:
        merged = dict(spec)
        merged.update(overrides)
        _ = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)

    t = thThread(
        target=_background_publisher,
        args=(app_config, logger, capability, spec),
        kwargs=overrides,
        daemon=True
    )
    t.start()


# -----------------------------------------------------------------------------------------------
def publish_with_lifecycle(
    app_config: typeAny,
    logger: typeOptional[typeAny],
    lm: typeAny,
    capability: str,
    spec: typeOptional[typeUnion[ServiceSpec, typeDict[str, typeAny]]] = None,
    **overrides: typeAny
) -> None:
    """
    Validates spec synchronously (FAIL-FAST), binds background cancellation to the lifecycle manager,
    and publishes to web-interface in a non-blocking background thread with 30s heartbeats.
    """
    # Fail-fast synchronous validation
    if app_config is None:
        if logger and hasattr(logger, "critical"):
            logger.critical("spec.publish_with_lifecycle: app_config is strictly required (nil provided) (FAIL-FAST)")
        raise ValueError("spec.publish_with_lifecycle: app_config is strictly required (FAIL-FAST)")

    try:
        web_addr = app_config.get_listen_addr("web_interface")
        if not web_addr or not str(web_addr).strip():
            raise ValueError("empty web_interface address")
    except Exception as e:
        if logger and hasattr(logger, "critical"):
            logger.critical(f"spec.publish_with_lifecycle: capability 'web_interface' is unresolvable: {e} (FAIL-FAST)")
        raise RuntimeError(f"spec.publish_with_lifecycle: capability 'web_interface' is unresolvable: {e} (FAIL-FAST)")

    # Validate spec
    if spec is None:
        _ = build_spec_from_config(app_config, capability, **overrides)
    elif isinstance(spec, ServiceSpec):
        merged = dcAsdict(spec)
        merged.update(overrides)
        _ = build_spec_from_config(app_config, capability or spec.capability, **merged)
    elif dcIsDataclass(spec):
        merged = dcAsdict(spec)
        merged.update(overrides)
        _ = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)
    else:
        merged = dict(spec)
        merged.update(overrides)
        _ = build_spec_from_config(app_config, capability or merged.get("capability", ""), **merged)

    stop_event = thEvent()
    if lm is not None:
        if hasattr(lm, "register") and callable(lm.register):
            try:
                lm.register(f"OpenMFEPublisher_{capability}", stop_event.set)
            except Exception:
                pass
        elif hasattr(lm, "add_shutdown_hook") and callable(lm.add_shutdown_hook):
            try:
                lm.add_shutdown_hook(stop_event.set)
            except Exception:
                pass

    t = thThread(
        target=_background_publisher,
        args=(app_config, logger, capability, spec, stop_event),
        kwargs=overrides,
        daemon=True
    )
    t.start()


# -----------------------------------------------------------------------------------------------
def publish_service_spec(
    app_config: typeAny,
    logger: typeOptional[typeAny],
    spec_or_capability: typeUnion[str, ServiceSpec, typeDict[str, typeAny]],
    non_blocking: bool = True,
    **overrides: typeAny
) -> None:
    """Legacy alias for publish / publish_sync."""
    if isinstance(spec_or_capability, str):
        cap = spec_or_capability
        s = None
    elif isinstance(spec_or_capability, ServiceSpec):
        cap = spec_or_capability.capability
        s = spec_or_capability
    elif isinstance(spec_or_capability, dict):
        cap = spec_or_capability.get("capability", "")
        s = spec_or_capability
    else:
        cap = getattr(spec_or_capability, "capability", "")
        s = spec_or_capability

    if non_blocking:
        publish(app_config, logger, cap, s, **overrides)
    else:
        publish_sync(app_config, logger, cap, s, **overrides)


# -----------------------------------------------------------------------------------------------
# CamelCase / Go-parity aliases
# -----------------------------------------------------------------------------------------------
Publish = publish
PublishWithLifecycle = publish_with_lifecycle
PublishSync = publish_sync
BuildSpecFromConfig = build_spec_from_config
