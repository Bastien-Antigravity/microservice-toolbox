import base64
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import time
from typing import Any

from .models import MarketEvent, MarketEventType


class BusinessEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode('utf-8')
        return super().default(obj)

def serialize(obj: Any) -> bytes:
    """Converts a business object into a JSON byte array."""
    return json.dumps(obj, cls=BusinessEncoder).encode('utf-8')

def deserialize(data: bytes, target_class: Any) -> Any:
    raw = json.loads(data.decode('utf-8'))

    # Handle base64 bytes for MarketEvent payload
    if target_class == MarketEvent and 'payload' in raw:
        raw['payload'] = base64.b64decode(raw['payload'])
        # Handle enum conversion
        if 'type' in raw:
            raw['type'] = MarketEventType(raw['type'])

    if is_dataclass(target_class):
        # Filter raw keys to match dataclass fields
        fields = target_class.__dataclass_fields__.keys()
        filtered = {k: v for k, v in raw.items() if k in fields}
        return target_class(**filtered)
    return raw

def wrap_market_event(symbol: str, exchange: str, event_type: MarketEventType, payload: Any) -> MarketEvent:
    """Creates a MarketEvent envelope for a payload."""
    serialized_payload = serialize(payload)
    ts = system_timestamp()

    return MarketEvent(
        event_id=f"{symbol}-{ts}",
        symbol=symbol,
        exchange=exchange,
        timestamp=ts,
        type=event_type,
        payload=serialized_payload
    )

def system_timestamp() -> int:
    """Returns the current unix timestamp in milliseconds."""
    return int(time.time() * 1000)
