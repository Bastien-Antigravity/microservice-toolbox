#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Cross-service and cross-brain mission trace correlation (X-Bastien-Mission-ID)
for Python microservices. Sanitizes, extracts, injects, and binds mission_id
across ASGI/FastAPI requests, NATS headers, ContextVar task state, and UniLog
structured metadata.

DATA FLOW:
1. Input: Inbound HTTP/NATS headers or X_BASTIEN_MISSION_ID environment variable.
2. Logic: Validates ASCII header safety, stores in ContextVar, and binds UniLog metadata.
3. Output: Propagated X-Bastien-Mission-ID header on responses and outbound requests.

KEY PARAMETERS:
- HEADER_MISSION_ID: Canonical wire header ('X-Bastien-Mission-ID').
- METADATA_KEY: Canonical universal-logger metadata key ('mission_id').
- ENV_MISSION_ID: Process environment seed ('X_BASTIEN_MISSION_ID').
"""

from contextvars import ContextVar as ctxContextVar
from os import getenv as osGetenv
from typing import Any as typeAny, Callable as typeCallable, Dict as typeDict, Mapping as typeMapping, Optional as typeOptional

# -----------------------------------------------------------------------------------------------

HEADER_MISSION_ID = "X-Bastien-Mission-ID"
METADATA_KEY = "mission_id"
ENV_MISSION_ID = "X_BASTIEN_MISSION_ID"
_MAX_MISSION_ID_LEN = 128

_ACTIVE_MISSION_ID: ctxContextVar[str] = ctxContextVar("bastien_mission_id", default="")

# -----------------------------------------------------------------------------------------------


def sanitize_mission_id(raw: typeOptional[str]) -> str:
    """Validates and trims a raw mission ID, rejecting whitespace or control characters."""
    if not raw:
        return ""
    trimmed = str(raw).strip()
    if not trimmed or len(trimmed) > _MAX_MISSION_ID_LEN:
        return ""
    for ch in trimmed:
        code = ord(ch)
        if code < 0x21 or code > 0x7E:
            return ""
    return trimmed


# -----------------------------------------------------------------------------------------------


def get_mission_id() -> str:
    """Returns the active task-scoped mission ID or falls back to X_BASTIEN_MISSION_ID."""
    current = _ACTIVE_MISSION_ID.get()
    if current:
        return current
    return sanitize_mission_id(osGetenv(ENV_MISSION_ID))


# -----------------------------------------------------------------------------------------------


def set_mission_id(mission_id: str, *, logger: typeOptional[typeAny] = None) -> str:
    """Sets the active task-scoped mission ID and optionally binds UniLog metadata."""
    clean = sanitize_mission_id(mission_id)
    _ACTIVE_MISSION_ID.set(clean)
    if clean and logger is not None:
        add_meta = getattr(logger, "add_metadata", None)
        if callable(add_meta):
            add_meta(METADATA_KEY, clean)
    return clean


# -----------------------------------------------------------------------------------------------


def bind_from_env(logger: typeOptional[typeAny]) -> str:
    """Binds X_BASTIEN_MISSION_ID to logger metadata during cold bootstrap if present."""
    clean = sanitize_mission_id(osGetenv(ENV_MISSION_ID))
    if clean:
        set_mission_id(clean, logger=logger)
    return clean


# -----------------------------------------------------------------------------------------------


def extract_from_headers(
    headers: typeMapping[str, str],
    *,
    logger: typeOptional[typeAny] = None,
) -> str:
    """Extracts X-Bastien-Mission-ID case-insensitively from an inbound header mapping."""
    found = headers.get(HEADER_MISSION_ID)
    if not found:
        target_lower = HEADER_MISSION_ID.lower()
        for key, val in headers.items():
            if str(key).lower() == target_lower:
                found = val
                break
    clean = sanitize_mission_id(found)
    if clean:
        set_mission_id(clean, logger=logger)
    return clean


# -----------------------------------------------------------------------------------------------


def inject_headers(headers: typeOptional[typeDict[str, str]] = None) -> typeDict[str, str]:
    """Injects the active X-Bastien-Mission-ID into an outbound HTTP/NATS header dictionary."""
    out = dict(headers) if headers is not None else {}
    mission_id = get_mission_id()
    if mission_id:
        out[HEADER_MISSION_ID] = mission_id
    return out


# -----------------------------------------------------------------------------------------------


class MissionIDMiddleware:
    """Zero-dependency ASGI middleware propagating X-Bastien-Mission-ID on HTTP requests."""

    Name = "MissionIDMiddleware"

    def __init__(self, app: typeCallable, *, logger: typeOptional[typeAny] = None) -> None:
        self.app = app
        self.logger = logger

    # -----------------------------------------------------------------------------------------------

    async def __call__(self, scope: typeDict[str, typeAny], receive: typeCallable, send: typeCallable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        target_bytes = HEADER_MISSION_ID.lower().encode("latin1")
        mission_id = ""
        for raw_k, raw_v in scope.get("headers") or ():
            if raw_k.lower() == target_bytes:
                mission_id = sanitize_mission_id(raw_v.decode("latin1", errors="ignore"))
                break
        if not mission_id:
            mission_id = sanitize_mission_id(osGetenv(ENV_MISSION_ID))

        token = _ACTIVE_MISSION_ID.set(mission_id)
        if mission_id and self.logger is not None:
            add_meta = getattr(self.logger, "add_metadata", None)
            if callable(add_meta):
                add_meta(METADATA_KEY, mission_id)

        async def send_with_header(message: typeDict[str, typeAny]) -> None:
            if mission_id and message.get("type") == "http.response.start":
                resp_headers = list(message.get("headers") or [])
                resp_headers.append((HEADER_MISSION_ID.encode("latin1"), mission_id.encode("latin1")))
                message = {**message, "headers": resp_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _ACTIVE_MISSION_ID.reset(token)
