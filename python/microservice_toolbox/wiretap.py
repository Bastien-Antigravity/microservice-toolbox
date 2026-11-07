#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides a distinct, lock-free switchable real-time transport telemetry wrapper
("WireTap") for Python microservices (gRPC, FastMCP/SSE, NATS, PostgreSQL/ChromaDB).
Tracks inter-service and external client connections (such as Antigravity IDE -> RAG MCP)
and segregated information channels (MCP tool names, RPC methods, NATS subjects).

DATA FLOW:
1. Input: Transport wrappers (TeleClient, FastMCP tool/ASGI middleware, gRPC server).
2. Logic: Lock-free boolean check (`is_enabled()`). When enabled, updates edge and
   segregated channel counters in memory.
3. Output: Periodic 2s non-blocking HTTP flush to web-interface (/api/v1/system/wiretap/ingest)
   with automatic synchronization of the global runtime ON/OFF switch.

KEY PARAMETERS:
- _enabled: Lock-free atomic-under-GIL boolean switch modifiable via config or UI toggle.
"""

from datetime import datetime, timezone
from json import dumps as jsonDumps, loads as jsonLoads
from threading import Thread as threadingThread
from time import sleep as timeSleep
from typing import Any, Dict, List
from urllib.request import Request as urllibRequest, urlopen as urllibUrlopen

# -----------------------------------------------------------------------------------------------
# Lock-Free Switch & Module State
# -----------------------------------------------------------------------------------------------

_enabled: bool = True
_local_service: str = ""
_web_hub_url: str = ""
_reporter_started: bool = False

# _edges maps "source|target|protocol" -> dict of edge metrics and channels dict
_edges: Dict[str, Dict[str, Any]] = {}


def set_enabled(on: bool) -> None:
    """Atomically switches real-time connection tracking ON or OFF without locks."""
    global _enabled
    _enabled = bool(on)


def is_enabled() -> bool:
    """Atomically returns whether real-time connection tracking is active."""
    return _enabled


def set_local_service(service_name: str) -> None:
    """Sets the canonical service identifier for this Python process."""
    global _local_service
    _local_service = normalize_service_id(service_name)


def get_local_service() -> str:
    """Returns the canonical service identifier for this Python process."""
    return _local_service


def normalize_service_id(raw: str) -> str:
    """Normalizes arbitrary service or component names into canonical mesh IDs."""
    s = (raw or "").strip().lower().replace("-", "_")
    if s in ("09_rag_engine", "rag_service", "obsidian_rag"):
        return "rag_engine"
    if s in ("08_squad_agent", "squad_agent"):
        return "agent_squad"
    if s in ("nats_server", "nats_broker"):
        return "nats"
    if s in ("postgres", "postgresql", "timescaledb"):
        return "timescale_db"
    if s == "vector_db":
        return "chromadb"
    return s


# -----------------------------------------------------------------------------------------------
# Configuration & Background Reporter
# -----------------------------------------------------------------------------------------------


def configure_from_config(service_name: str, config: Any) -> None:
    """
    Initializes WireTap from validated AppConfig and starts the background reporter daemon thread.
    """
    global _web_hub_url, _reporter_started

    set_local_service(service_name)

    raw_enabled = str(config.get_local("wiretap_enabled") or config.common.get("wiretap_enabled") or "true")
    set_enabled(raw_enabled.lower() == "true")

    web_addr = config.get_listen_addr("web_interface")
    _web_hub_url = f"http://{web_addr}"

    if not _reporter_started and _local_service != "web_interface":
        _reporter_started = True
        t = threadingThread(target=_reporter_loop, name="wiretap-reporter", daemon=True)
        t.start()


# -----------------------------------------------------------------------------------------------
# Hot-Path Event Recording (Zero-Lock Fast Exit When Disabled)
# -----------------------------------------------------------------------------------------------


def record_event(
    source: str,
    target: str,
    protocol: str,
    framing: str,
    channel: str,
    category: str = "data",
    direction: str = "outbound",
    payload_summary: str = "",
    bytes_count: int = 0,
    latency_ms: float = 0.0,
    is_err: bool = False,
    is_external: bool = False,
    conn_delta: int = 0,
) -> None:
    """
    Records a real-time transport event and segregated channel metric if enabled.
    Immediately returns if `_enabled` is False.
    """
    if not _enabled:
        return

    src_norm = normalize_service_id(source)
    tgt_norm = normalize_service_id(target)
    if not src_norm or not tgt_norm:
        return

    proto_upper = (protocol or "TCP").strip().upper()
    ch_name = channel or f"{proto_upper.lower()}:default"
    edge_key = f"{src_norm}|{tgt_norm}|{proto_upper}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    edge = _edges.get(edge_key)
    if edge is None:
        edge = {
            "source": src_norm,
            "target": tgt_norm,
            "protocol": proto_upper,
            "framing": framing or proto_upper,
            "active_conns": 1 if conn_delta >= 0 else 0,
            "total_frames": 0,
            "total_bytes": 0,
            "total_errors": 0,
            "last_seen": now_iso,
            "is_external": bool(is_external),
            "channels": {},
        }
        _edges[edge_key] = edge
    else:
        if framing:
            edge["framing"] = framing
        if is_external:
            edge["is_external"] = True
        if conn_delta != 0:
            edge["active_conns"] = max(0, int(edge.get("active_conns", 0)) + conn_delta)
        elif int(edge.get("active_conns", 0)) == 0:
            edge["active_conns"] = 1

    edge["total_frames"] = int(edge.get("total_frames", 0)) + 1
    if bytes_count > 0:
        edge["total_bytes"] = int(edge.get("total_bytes", 0)) + int(bytes_count)
    if is_err:
        edge["total_errors"] = int(edge.get("total_errors", 0)) + 1
    edge["last_seen"] = now_iso

    channels_map: Dict[str, Dict[str, Any]] = edge["channels"]
    ch_entry = channels_map.get(ch_name)
    if ch_entry is None:
        ch_entry = {
            "channel": ch_name,
            "category": category or "data",
            "direction": direction or "outbound",
            "frames": 0,
            "bytes": 0,
            "errors": 0,
            "total_lat_ms": 0.0,
            "lat_samples": 0,
            "avg_latency_ms": 0.0,
            "last_seen": now_iso,
            "last_payload": "",
        }
        channels_map[ch_name] = ch_entry

    ch_entry["frames"] = int(ch_entry["frames"]) + 1
    if bytes_count > 0:
        ch_entry["bytes"] = int(ch_entry["bytes"]) + int(bytes_count)
    if is_err:
        ch_entry["errors"] = int(ch_entry["errors"]) + 1
    if latency_ms > 0:
        ch_entry["total_lat_ms"] = float(ch_entry["total_lat_ms"]) + float(latency_ms)
        ch_entry["lat_samples"] = int(ch_entry["lat_samples"]) + 1
        ch_entry["avg_latency_ms"] = round(
            ch_entry["total_lat_ms"] / max(1, ch_entry["lat_samples"]), 3
        )
    ch_entry["last_seen"] = now_iso
    if payload_summary:
        ch_entry["last_payload"] = str(payload_summary)[:160]


def snapshot() -> List[Dict[str, Any]]:
    """Returns a serializable list of EdgeReport dicts."""
    out: List[Dict[str, Any]] = []
    for edge in list(_edges.values()):
        ch_list = []
        for ch in list(edge.get("channels", {}).values()):
            ch_list.append({
                "channel": ch["channel"],
                "category": ch["category"],
                "direction": ch["direction"],
                "frames": ch["frames"],
                "bytes": ch["bytes"],
                "errors": ch["errors"],
                "avg_latency_ms": ch["avg_latency_ms"],
                "last_seen": ch["last_seen"],
                "last_payload": ch["last_payload"],
            })
        ch_list.sort(key=lambda x: x["channel"])
        out.append({
            "source": edge["source"],
            "target": edge["target"],
            "protocol": edge["protocol"],
            "framing": edge["framing"],
            "active_conns": edge["active_conns"],
            "total_frames": edge["total_frames"],
            "total_bytes": edge["total_bytes"],
            "total_errors": edge["total_errors"],
            "last_seen": edge["last_seen"],
            "is_external": edge["is_external"],
            "channels": ch_list,
        })
    out.sort(key=lambda x: (x["source"], x["target"], x["protocol"]))
    return out


def reset() -> None:
    """Clears all recorded edges (useful for unit tests)."""
    _edges.clear()


# -----------------------------------------------------------------------------------------------
# FastMCP / External Client Middleware & Tool Wrapper
# -----------------------------------------------------------------------------------------------


def record_mcp_tool_call(
    tool_name: str,
    caller: str = "antigravity_ide",
    bytes_count: int = 0,
    latency_ms: float = 0.0,
    is_err: bool = False,
) -> None:
    """
    Records an inbound MCP tool invocation on rag_mcp from an external client
    (such as Antigravity IDE).
    """
    if not _enabled:
        return
    record_event(
        source=caller or "antigravity_ide",
        target="rag_mcp",
        protocol="SSE",
        framing="Port 8090 FastMCP (SSE/JSON-RPC)",
        channel=f"mcp:tool:{tool_name}",
        category="mcp_tool",
        direction="inbound",
        payload_summary=tool_name,
        bytes_count=bytes_count,
        latency_ms=latency_ms,
        is_err=is_err,
        is_external=True,
    )


def _reporter_loop() -> None:
    while True:
        timeSleep(2.0)
        try:
            edges_data = snapshot() if _enabled else []
            payload = {
                "reporter": _local_service,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "enabled": _enabled,
                "edges": edges_data,
            }
            data_bytes = jsonDumps(payload).encode("utf-8")
            req = urllibRequest(
                f"{_web_hub_url}/api/v1/system/wiretap/ingest",
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllibUrlopen(req, timeout=1.5) as resp:
                resp_body = resp.read().decode("utf-8")
                if resp_body:
                    parsed = jsonLoads(resp_body)
                    if isinstance(parsed, dict) and "enabled" in parsed:
                        remote_enabled = bool(parsed["enabled"])
                        if remote_enabled != _enabled:
                            set_enabled(remote_enabled)
        except Exception:
            pass

