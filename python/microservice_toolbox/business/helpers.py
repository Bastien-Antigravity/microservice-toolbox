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
from dataclasses import asdict as dcAsdict, fields as dcFields, is_dataclass as dcIs_dataclass
from enum import Enum as enumEnum
from json import JSONEncoder as jsonJSONEncoder, dumps as jsonDumps, loads as jsonLoads
from time import time as timeTime
from typing import (
    Any as typeAny,
    get_args as typeGetArgs,
    get_origin as typeGetOrigin,
    get_type_hints as typeGetTypeHints,
)

from .models import MarketEvent, MarketEventType

# -----------------------------------------------------------------------------------------------


class BusinessEncoder(jsonJSONEncoder):
    """JSON encoder that handles dataclasses, enums, and byte arrays."""

    Name = "BusinessEncoder"

    # -----------------------------------------------------------------------------------------------

    def default(self, obj: typeAny) -> typeAny:
        if dcIs_dataclass(obj):
            return dcAsdict(obj)
        if isinstance(obj, enumEnum):
            return obj.value
        if isinstance(obj, (bytes, bytearray)):
            return base64B64Encode(bytes(obj)).decode("utf-8")
        return super().default(obj)


# -----------------------------------------------------------------------------------------------


def _coerce_value(value: typeAny, target_type: typeAny) -> typeAny:
    """Recursively coerces decoded JSON values to target dataclass, Enum, or bytes types."""
    if value is None:
        return None
    origin = typeGetOrigin(target_type)
    if origin in (list, tuple) and isinstance(value, list):
        item_types = typeGetArgs(target_type)
        elem_type = item_types[0] if item_types else typeAny
        return [_coerce_value(item, elem_type) for item in value]
    if isinstance(target_type, type):
        if target_type is bytes and isinstance(value, str):
            return base64B64Decode(value)
        if issubclass(target_type, enumEnum) and not isinstance(value, target_type):
            return target_type(value)
        if dcIs_dataclass(target_type) and isinstance(value, dict):
            return _coerce_dataclass(value, target_type)
    return value


def _coerce_dataclass(raw: dict, target_class: typeAny) -> typeAny:
    hints = typeGetTypeHints(target_class)
    field_names = {f.name for f in dcFields(target_class)}
    kwargs = {}
    for name in field_names:
        if name in raw:
            kwargs[name] = _coerce_value(raw[name], hints.get(name, typeAny))
    return target_class(**kwargs)


# -----------------------------------------------------------------------------------------------


def serialize(obj: typeAny) -> bytes:
    """Converts a business object into a JSON byte array."""
    return jsonDumps(obj, cls=BusinessEncoder).encode("utf-8")


# -----------------------------------------------------------------------------------------------


def deserialize(data: bytes, target_class: typeAny) -> typeAny:
    """Converts a JSON byte array back into a business object or dataclass."""
    raw = jsonLoads(data.decode("utf-8"))
    if dcIs_dataclass(target_class) and isinstance(raw, dict):
        return _coerce_dataclass(raw, target_class)
    return raw


# -----------------------------------------------------------------------------------------------


def wrap_market_event(symbol: str, exchange: str, event_type: MarketEventType, payload: typeAny) -> MarketEvent:
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
