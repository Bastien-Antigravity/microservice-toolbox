#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides serialization and deserialization utilities for business models.
Includes custom JSON encoding for dataclasses, enums, and byte arrays to ensure
ecosystem-wide data parity.

DATA FLOW:
1. Business objects are passed to serialize().
2. The custom BusinessEncoder handles complex types.
3. deserialize() reconstructs objects using target class definitions.

KEY PARAMETERS:
- BusinessEncoder: Custom JSON encoder for ecosystem-standard types.
"""

from base64 import b64decode as base64B64Decode, b64encode as base64B64Encode
from dataclasses import asdict as dcAsdict, is_dataclass as dcIs_dataclass
from enum import Enum
from json import JSONEncoder as jsonJSONEncoder, dumps as jsonDumps, loads as jsonLoads
from time import time as timeTime
from typing import Any

from .models import MarketEvent, MarketEventType

# -----------------------------------------------------------------------------------------------


class BusinessEncoder(jsonJSONEncoder):
    """JSON encoder that handles dataclasses, enums, and byte arrays."""

    Name = "BusinessEncoder"

    # -----------------------------------------------------------------------------------------------

    def default(self, obj: Any) -> Any:
        if dcIs_dataclass(obj):
            return dcAsdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, bytes):
            return base64B64Encode(obj).decode("utf-8")
        return super().default(obj)


# -----------------------------------------------------------------------------------------------


def serialize(obj: Any) -> bytes:
    """Converts a business object into a JSON byte array."""
    return jsonDumps(obj, cls=BusinessEncoder).encode("utf-8")


# -----------------------------------------------------------------------------------------------


def deserialize(data: bytes, target_class: Any) -> Any:
    """Converts a JSON byte array back into a business object or dataclass."""
    raw = jsonLoads(data.decode("utf-8"))

    # Handle base64 bytes for MarketEvent payload
    if target_class == MarketEvent and "payload" in raw:
        raw["payload"] = base64B64Decode(raw["payload"])
        # Handle enum conversion
        if "type" in raw:
            raw["type"] = MarketEventType(raw["type"])

    if dcIs_dataclass(target_class):
        # Filter raw keys to match dataclass fields
        fields = target_class.__dataclass_fields__.keys()
        filtered = {k: v for k, v in raw.items() if k in fields}
        return target_class(**filtered)
    return raw


# -----------------------------------------------------------------------------------------------


def wrap_market_event(symbol: str, exchange: str, event_type: MarketEventType, payload: Any) -> MarketEvent:
    """Creates a MarketEvent envelope for a payload."""
    serialized_payload = serialize(payload)
    ts = system_timestamp()

    return MarketEvent(
        event_id=f"{symbol}-{ts}", symbol=symbol, exchange=exchange, timestamp=ts, type=event_type, payload=serialized_payload
    )


# -----------------------------------------------------------------------------------------------


def system_timestamp() -> int:
    """Returns the current unix timestamp in milliseconds."""
    return int(timeTime() * 1000)
