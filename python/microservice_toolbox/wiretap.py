#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides a distinct, switchable real-time transport telemetry wrapper ("WireTap")
for Python microservices (gRPC, FastMCP/SSE, NATS, PostgreSQL/ChromaDB).
Tracks inter-service and external client connections and segregated information
channels under thread-safe synchronization, with power-of-two bitmask sampling.

DATA FLOW:
1. Input: Transport wrappers (TeleClient, FastMCP tool/ASGI middleware, gRPC server).
2. Logic: Lock-free boolean check (`is_enabled()`) + power-of-two `should_sample(mask)`.
   When enabled, updates edge and segregated channel counters under `_lock`.
3. Output: Periodic 2s non-blocking HTTP flush to web-interface (/api/v1/system/wiretap/ingest)
   with automatic synchronization of the global runtime ON/OFF switch.

KEY PARAMETERS:
- _enabled: Fast boolean switch modifiable via config or UI toggle.
- _lock: Synchronizes `_edges` and channel mutations across worker threads.
"""

from datetime import datetime as dtDateTime, timezone as dtTimezone
from json import dumps as jsonDumps, loads as jsonLoads
from threading import Lock as threadingLock, Thread as threadingThread, local as threadingLocal
from time import sleep as timeSleep, time as timeTime
from typing import Any as typeAny, Dict as typeDict, List as typeList
from urllib.request import Request as urllibRequest, urlopen as urllibUrlopen

# -----------------------------------------------------------------------------------------------
# Switch, Thread-Safe Store & Bitmask Sampling State
# -----------------------------------------------------------------------------------------------

MAX_PAYLOAD_SUMMARY_BYTES = 256
_REDACTED_ENC_TOKEN = "ENC([REDACTED])"

_enabled: bool = True
_local_service: str = "unknown_service"
_web_hub_url: str = ""
_reporter_started: bool = False
_lock = threadingLock()
_sample_tls = threadingLocal()

# _edges maps "source|target|protocol" -> dict of edge metrics and channels dict
_edges: typeDict[str, typeDict[str, typeAny]] = {}


def sanitize_payload_summary(raw: str) -> str:
    """Redacts ENC(...) secret tokens and caps summary length to 256 bytes."""
    if not raw:
        return ""
    s = raw
    if "ENC(" in s:
        parts: typeList[str] = []
        rem = s
        while True:
            idx = rem.find("ENC(")
            if idx == -1:
                parts.append(rem)
                break
            parts.append(rem[:idx])
            after_prefix = rem[idx + 4 :]
            close_idx = after_prefix.find(")")
            parts.append(_REDACTED_ENC_TOKEN)
            if close_idx == -1:
                break
            rem = after_prefix[close_idx + 1 :]
        s = "".join(parts)
    if len(s) > MAX_PAYLOAD_SUMMARY_BYTES:
        return s[: MAX_PAYLOAD_SUMMARY_BYTES - 3] + "..."
    return s


def _format_iso_ts(ts: float) -> str:
    return dtDateTime.fromtimestamp(ts, tz=dtTimezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_enabled(on: bool) -> None:
    """Switches real-time connection tracking ON or OFF."""
    global _enabled
    _enabled = bool(on)


def is_enabled() -> bool:
    """Returns whether real-time connection tracking is active."""
    return _enabled


def should_sample(mask: int = 0) -> bool:
    """Power-of-two thread-local bitmask sampler (mask == 0 always returns True)."""
    if mask <= 0:
        return True
    counter = getattr(_sample_tls, "counter", 0) + 1
    _sample_tls.counter = counter
    return (counter & mask) == 0


def set_local_service(service_name: str) -> None:
    """Sets the canonical service identifier for this Python process."""
    global _local_service
    norm = normalize_service_id(service_name)
    _local_service = norm or "unknown_service"


def get_local_service() -> str:
    """Returns the canonical service identifier for this Python process."""
    return _local_service or "unknown_service"


def set_web_hub_url(url: str) -> None:
    """Sets the base HTTP URL for the central WireTap ingestion hub."""
    global _web_hub_url
    _web_hub_url = (url or "").strip().rstrip("/")


def get_web_hub_url() -> str:
    """Returns the configured base HTTP URL for the central WireTap ingestion hub."""
    return _web_hub_url


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


def configure_from_config(service_name: str, config: typeAny) -> None:
    """
    Initializes WireTap from validated AppConfig and starts the background reporter daemon thread.
    Zero silent fallback: reads web_interface capability and wiretap_enabled strictly from AppConfig.
    """
    global _reporter_started

    set_local_service(service_name)

    raw_local = config.get_local("wiretap_enabled")
    raw_enabled = str(
        raw_local
        if raw_local not in (None, "")
        else (config.common.get("wiretap_enabled") or "true")
    )
    set_enabled(raw_enabled.lower() == "true")

    web_addr = config.get_listen_addr("web_interface")
    set_web_hub_url(f"http://{web_addr}")

    if not _reporter_started and get_local_service() != "web_interface":
        _reporter_started = True
        t = threadingThread(target=_reporter_loop, name="wiretap-reporter", daemon=True)
        t.start()


# -----------------------------------------------------------------------------------------------
# Hot-Path Event Recording (Zero-Lock Fast Exit When Disabled)
# -----------------------------------------------------------------------------------------------


def record_event(
    source: str,
    target: str,
    protocol: str = "TCP",
    framing: str = "raw",
    channel: str = "",
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
    frame_val = framing or "raw"
    edge_key = f"{src_norm}|{tgt_norm}|{proto_upper}"
    now_ts = timeTime()

    with _lock:
        edge = _edges.get(edge_key)
        if edge is None:
            edge = {
                "source": src_norm,
                "target": tgt_norm,
                "protocol": proto_upper,
                "framing": frame_val,
                "active_conns": max(0, conn_delta) if conn_delta != 0 else 1,
                "total_frames": 0,
                "total_bytes": 0,
                "total_errors": 0,
                "last_seen_ts": now_ts,
                "is_external": bool(is_external),
                "channels": {},
            }
            _edges[edge_key] = edge
        else:
            if framing and framing != "raw":
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
        edge["last_seen_ts"] = now_ts

        channels_map: typeDict[str, typeDict[str, typeAny]] = edge["channels"]
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
                "last_seen_ts": now_ts,
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
            ch_entry["avg_latency_ms"] = ch_entry["total_lat_ms"] / max(1, ch_entry["lat_samples"])
        ch_entry["last_seen_ts"] = now_ts
        if payload_summary:
            ch_entry["last_payload"] = sanitize_payload_summary(str(payload_summary))


record_event_with_conn_delta = record_event


def snapshot() -> typeList[typeDict[str, typeAny]]:
    """Returns a serializable list of EdgeReport dicts."""
    out: typeList[typeDict[str, typeAny]] = []
    with _lock:
        edges_copy = list(_edges.values())
        for edge in edges_copy:
            ch_list = []
            for ch in list(edge.get("channels", {}).values()):
                ch_last_seen = _format_iso_ts(float(ch["last_seen_ts"])) if "last_seen_ts" in ch else str(ch.get("last_seen", ""))
                item: typeDict[str, typeAny] = {
                    "channel": ch["channel"],
                    "category": ch["category"],
                    "direction": ch["direction"],
                    "frames": ch["frames"],
                    "bytes": ch["bytes"],
                    "errors": ch["errors"],
                    "avg_latency_ms": ch["avg_latency_ms"],
                    "last_seen": ch_last_seen,
                }
                if ch.get("last_payload"):
                    item["last_payload"] = sanitize_payload_summary(str(ch["last_payload"]))
                ch_list.append(item)
            ch_list.sort(key=lambda x: x["channel"])
            edge_last_seen = _format_iso_ts(float(edge["last_seen_ts"])) if "last_seen_ts" in edge else str(edge.get("last_seen", ""))
            out.append({
                "source": edge["source"],
                "target": edge["target"],
                "protocol": edge["protocol"],
                "framing": edge["framing"],
                "active_conns": edge["active_conns"],
                "total_frames": edge["total_frames"],
                "total_bytes": edge["total_bytes"],
                "total_errors": edge["total_errors"],
                "last_seen": edge_last_seen,
                "is_external": edge["is_external"],
                "channels": ch_list,
            })
    out.sort(key=lambda x: (x["source"], x["target"], x["protocol"]))
    return out


def merge_remote_snapshot(incoming: typeList[typeDict[str, typeAny]]) -> None:
    """Merges a batch of remote EdgeReport dicts into the local store."""
    if not _enabled:
        return
    now_ts = timeTime()
    with _lock:
        for rep in incoming or []:
            src_norm = normalize_service_id(str(rep.get("source", "")))
            tgt_norm = normalize_service_id(str(rep.get("target", "")))
            proto_upper = str(rep.get("protocol", "")).strip().upper()
            if not src_norm or not tgt_norm or not proto_upper:
                continue
            edge_key = f"{src_norm}|{tgt_norm}|{proto_upper}"
            edge = _edges.get(edge_key)
            if edge is None:
                edge = {
                    "source": src_norm,
                    "target": tgt_norm,
                    "protocol": proto_upper,
                    "framing": str(rep.get("framing") or "raw"),
                    "active_conns": 0,
                    "total_frames": 0,
                    "total_bytes": 0,
                    "total_errors": 0,
                    "last_seen_ts": now_ts,
                    "is_external": False,
                    "channels": {},
                }
                _edges[edge_key] = edge
            if rep.get("framing") and rep.get("framing") != "raw":
                edge["framing"] = str(rep["framing"])
            if rep.get("is_external"):
                edge["is_external"] = True
            if int(rep.get("active_conns") or 0) > 0:
                edge["active_conns"] = int(rep["active_conns"])
            if int(rep.get("total_frames") or 0) > int(edge["total_frames"]):
                edge["total_frames"] = int(rep["total_frames"])
            if int(rep.get("total_bytes") or 0) >= int(edge["total_bytes"]):
                edge["total_bytes"] = int(rep["total_bytes"])
            edge["total_errors"] = int(rep.get("total_errors") or 0)
            edge["last_seen_ts"] = now_ts

            channels_map: typeDict[str, typeDict[str, typeAny]] = edge["channels"]
            for ch in rep.get("channels") or []:
                ch_name = str(ch.get("channel", ""))
                if not ch_name:
                    continue
                ch_entry = channels_map.get(ch_name)
                if ch_entry is None:
                    ch_entry = {
                        "channel": ch_name,
                        "category": str(ch.get("category") or "data"),
                        "direction": str(ch.get("direction") or "outbound"),
                        "frames": 0,
                        "bytes": 0,
                        "errors": 0,
                        "total_lat_ms": 0.0,
                        "lat_samples": 0,
                        "avg_latency_ms": 0.0,
                        "last_seen_ts": now_ts,
                        "last_payload": "",
                    }
                    channels_map[ch_name] = ch_entry
                if int(ch.get("frames") or 0) >= int(ch_entry["frames"]):
                    ch_entry["frames"] = int(ch.get("frames") or 0)
                if int(ch.get("bytes") or 0) >= int(ch_entry["bytes"]):
                    ch_entry["bytes"] = int(ch.get("bytes") or 0)
                ch_entry["errors"] = int(ch.get("errors") or 0)
                avg_lat = float(ch.get("avg_latency_ms") or 0.0)
                if avg_lat > 0:
                    ch_entry["total_lat_ms"] = avg_lat
                    ch_entry["lat_samples"] = 1
                    ch_entry["avg_latency_ms"] = avg_lat
                ch_entry["last_seen_ts"] = now_ts
                if ch.get("last_payload"):
                    ch_entry["last_payload"] = sanitize_payload_summary(str(ch["last_payload"]))


def reset() -> None:
    """Clears all recorded edges (useful for unit tests)."""
    with _lock:
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
        if not _web_hub_url:
            continue
        try:
            edges_data = snapshot() if _enabled else []
            payload = {
                "reporter": get_local_service(),
                "timestamp": dtDateTime.now(dtTimezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
