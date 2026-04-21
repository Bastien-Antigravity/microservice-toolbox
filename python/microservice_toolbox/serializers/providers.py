import json
from typing import Any, Type

import msgpack

from .serializer import ISerializer, T


class JSONSerializer(ISerializer):
    """
    JSONSerializer implements Serializer natively over JSON.
    """
    def marshal(self, data: Any) -> bytes:
        try:
            return json.dumps(data).encode('utf-8')
        except (TypeError, ValueError) as e:
            raise ValueError(f"json marshal error: {e}")

    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        try:
            return json.loads(data.decode('utf-8'))
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"json unmarshal error: {e}")

class BinSerializer(ISerializer):
    """
    BinSerializer implements Serializer using Python's msgpack encoding.
    Note: matched with Go's 'BinSerializer' using msgpack.
    """
    def marshal(self, data: Any) -> bytes:
        try:
            return msgpack.packb(data, use_bin_type=True)
        except (TypeError, ValueError, Exception) as e:
            raise ValueError(f"msgpack marshal error: {e}")

    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        try:
            return msgpack.unpackb(data, raw=False)
        except (TypeError, ValueError, Exception) as e:
            raise ValueError(f"msgpack unmarshal error: {e}")

def new_json_serializer() -> ISerializer:
    return JSONSerializer()

def new_bin_serializer() -> ISerializer:
    return BinSerializer()
