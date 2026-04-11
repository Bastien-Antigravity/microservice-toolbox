import json
import pickle
from typing import Any, Type, TypeVar
from .serializer import Serializer, T

class JSONSerializer(Serializer):
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

class BinSerializer(Serializer):
    """
    BinSerializer implements Serializer using Python's pickle encoding.
    Note: matched with Go's 'BinSerializer' but using pickle as gob equivalent.
    """
    def marshal(self, data: Any) -> bytes:
        try:
            return pickle.dumps(data)
        except (pickle.PickleError, TypeError) as e:
            raise ValueError(f"pickle marshal error: {e}")

    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        try:
            return pickle.loads(data)
        except (pickle.PickleError, TypeError) as e:
            raise ValueError(f"pickle unmarshal error: {e}")

def NewJSONSerializer() -> Serializer:
    return JSONSerializer()

def NewBinSerializer() -> Serializer:
    return BinSerializer()
