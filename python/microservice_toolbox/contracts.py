#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Defines canonical, microservice-authored Exchange Contract models and live
introspection helpers for Python microservices (rag_engine, rag_mcp, squad_agent).

DATA FLOW:
1. Services build ExchangeContract descriptors from live FastAPI routes, local
   .proto IDL files, MCP tool catalogs, NATS topics, and PostgreSQL schemas.
2. build_contracts_envelope() packages contracts for GET /api/v1/contracts.
3. publish_service_spec(..., contracts=...) persists contracts in web-interface.

KEY PARAMETERS:
- ExchangeContract: Serializable typed contract block mapped 1-to-1 to UI tabs.
- extract_fastapi_operations: Introspects live FastAPI/Starlette routes.
- extract_proto_operations: Extracts RPC signatures directly from raw .proto IDL.
"""

from dataclasses import asdict as dcAsdict, dataclass as dcDataclass, field as dcField
from datetime import datetime as dtDatetime, timezone as dtTimezone
from pathlib import Path as pathPath
import re as reMod
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional, Sequence as typeSequence


# -----------------------------------------------------------------------------------------------
@dcDataclass
class ContractPeer:
    service: str
    role: str
    description: str = ""

    def to_dict(self) -> typeDict[str, typeAny]:
        d: typeDict[str, typeAny] = {
            "service": self.service,
            "role": self.role,
        }
        if self.description:
            d["description"] = self.description
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
@dcDataclass
class ContractOperation:
    name: str
    kind: str
    target: str
    input: str = ""
    output: str = ""
    description: str = ""

    def to_dict(self) -> typeDict[str, typeAny]:
        d: typeDict[str, typeAny] = {
            "name": self.name,
            "kind": self.kind,
            "target": self.target,
        }
        if self.input:
            d["input"] = self.input
        if self.output:
            d["output"] = self.output
        if self.description:
            d["description"] = self.description
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
@dcDataclass
class ExchangeContract:
    id: str
    type: str
    tab_label: str = ""
    icon: str = "fa-exchange"
    direction: str = "inbound"
    transport: str = ""
    address: str = ""
    port: int = 0
    framing: str = ""
    auth: str = ""
    summary: str = ""
    source: str = ""
    peers: typeList[ContractPeer] = dcField(default_factory=list)
    operations: typeList[ContractOperation] = dcField(default_factory=list)
    schema_format: str = ""
    schema: str = ""

    def to_dict(self) -> typeDict[str, typeAny]:
        d: typeDict[str, typeAny] = {
            "id": self.id,
            "type": self.type,
        }
        if self.tab_label:
            d["tabLabel"] = self.tab_label
        if self.icon:
            d["icon"] = self.icon
        if self.direction:
            d["direction"] = self.direction
        if self.transport:
            d["transport"] = self.transport
        if self.address:
            d["address"] = self.address
        if self.port:
            d["port"] = int(self.port)
        if self.framing:
            d["framing"] = self.framing
        if self.auth:
            d["auth"] = self.auth
        if self.summary:
            d["summary"] = self.summary
        if self.source:
            d["source"] = self.source
        if self.peers:
            d["peers"] = [p.to_dict() if hasattr(p, "to_dict") else p for p in self.peers]
        if self.operations:
            d["operations"] = [o.to_dict() if hasattr(o, "to_dict") else o for o in self.operations]
        if self.schema_format:
            d["schemaFormat"] = self.schema_format
        if self.schema:
            d["schema"] = self.schema
        return d

    toDict = to_dict


# -----------------------------------------------------------------------------------------------
def display_address(addr: str) -> str:
    clean = (addr or "").strip()
    if not clean:
        return "dynamic"
    if clean.startswith(":"):
        return f"127.0.0.1{clean}"
    if clean.startswith("0.0.0.0:"):
        return "127.0.0.1:" + clean[len("0.0.0.0:"):]
    return clean


def resolve_contract_port(addr: str) -> int:
    clean = (addr or "").strip()
    if not clean or ":" not in clean:
        return 0
    try:
        return int(clean.rsplit(":", 1)[-1])
    except ValueError:
        return 0


def build_contracts_envelope(
    service: str,
    version: str,
    source: str,
    contracts: typeSequence[typeAny],
) -> typeDict[str, typeAny]:
    serialized = [
        c.to_dict() if hasattr(c, "to_dict") else (dcAsdict(c) if hasattr(c, "__dataclass_fields__") else c)
        for c in (contracts or [])
    ]
    return {
        "service": service,
        "version": version or "0.0.1",
        "reliable": True,
        "exhaustive": True,
        "generatedAt": dtDatetime.now(dtTimezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source or f"{service} runtime introspection",
        "contracts": serialized,
    }


def extract_fastapi_operations(
    app: typeAny,
    include_prefixes: typeOptional[typeSequence[str]] = None,
    exclude_paths: typeOptional[typeSequence[str]] = None,
) -> typeList[ContractOperation]:
    """Introspects registered routes on a FastAPI app into ContractOperation items."""
    ops: typeList[ContractOperation] = []
    if app is None:
        return ops
    excluded = set(exclude_paths or ())
    seen = set()
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "")
        if not path or path in excluded:
            continue
        if path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            continue
        if include_prefixes and not any(path.startswith(pfx) for pfx in include_prefixes):
            continue
        methods = sorted(m for m in (getattr(route, "methods", None) or []) if m not in ("HEAD", "OPTIONS"))
        if not methods:
            continue
        endpoint_fn = getattr(route, "endpoint", None)
        doc = ""
        if endpoint_fn and getattr(endpoint_fn, "__doc__", None):
            doc = " ".join(line.strip() for line in endpoint_fn.__doc__.strip().splitlines())
        name = getattr(route, "name", "") or path
        for method in methods:
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            ops.append(
                ContractOperation(
                    name=name,
                    kind=method,
                    target=path,
                    description=doc or f"FastAPI handler {name}",
                )
            )
    ops.sort(key=lambda o: (o.target, o.kind))
    return ops


def read_schema_file(file_path: typeAny) -> str:
    p = pathPath(file_path)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return ""


def extract_proto_operations(proto_text: str) -> typeList[ContractOperation]:
    """Parses protobuf service and rpc declarations from raw .proto IDL text."""
    ops: typeList[ContractOperation] = []
    if not proto_text:
        return ops
    pkg_match = reMod.search(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;", proto_text, reMod.MULTILINE)
    pkg_prefix = f"{pkg_match.group(1)}." if pkg_match else ""
    svc_blocks = reMod.finditer(r"service\s+([A-Za-z0-9_]+)\s*\{([^}]*)\}", proto_text, reMod.DOTALL)
    rpc_re = reMod.compile(r"rpc\s+([A-Za-z0-9_]+)\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)\s+returns\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)")
    for blk in svc_blocks:
        svc_name = blk.group(1)
        body = blk.group(2)
        for m in rpc_re.finditer(body):
            rpc_name, req_stream, req_type, resp_stream, resp_type = m.groups()
            if req_stream and resp_stream:
                kind = "BIDI_STREAM"
            elif resp_stream:
                kind = "SERVER_STREAM"
            elif req_stream:
                kind = "CLIENT_STREAM"
            else:
                kind = "RPC"
            ops.append(
                ContractOperation(
                    name=rpc_name,
                    kind=kind,
                    target=f"{pkg_prefix}{svc_name}/{rpc_name}",
                    input=f"{'stream ' if req_stream else ''}{req_type}",
                    output=f"{'stream ' if resp_stream else ''}{resp_type}",
                    description=f"{svc_name}.{rpc_name}",
                )
            )
    return ops
