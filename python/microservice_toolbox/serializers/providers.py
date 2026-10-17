#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
Provides concrete implementations of Serializer for JSON and Binary (MessagePack) formats.
Ensures cross-language compatibility by using standard encoding protocols.

DATA FLOW:
1. Data structures are converted to bytes via marshal.
2. Bytes are converted back to data structures via unmarshal.

KEY PARAMETERS:
- data: The object to be serialized.
- cls: The target type for deserialization.
"""

from json import JSONDecodeError as jsonJSONDecodeError, dumps as jsonDumps, loads as jsonLoads
from typing import Any, Type

from msgpack import packb as msgpackPackb, unpackb as msgpackUnpackb

from .serializer import Serializer, T

# -----------------------------------------------------------------------------------------------


class JSONSerializer(Serializer):
    """
    JSONSerializer implements Serializer natively over JSON.
    """

    Name = "JSONSerializer"

    # -----------------------------------------------------------------------------------------------

    def marshal(self, data: Any) -> bytes:
        try:
            return jsonDumps(data).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise ValueError("{0} : json marshal error: {1}".format(self.Name, e))

    # -----------------------------------------------------------------------------------------------

    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        try:
            return jsonLoads(data.decode("utf-8"))
        except (TypeError, ValueError, jsonJSONDecodeError) as e:
            raise ValueError("{0} : json unmarshal error: {1}".format(self.Name, e))


# -----------------------------------------------------------------------------------------------


class BinSerializer(Serializer):
    """
    BinSerializer implements Serializer using Python's msgpack encoding.
    Note: matched with Go's 'BinSerializer' using msgpack.
    """

    Name = "BinSerializer"

    # -----------------------------------------------------------------------------------------------

    def marshal(self, data: Any) -> bytes:
        try:
            return msgpackPackb(data, use_bin_type=True)
        except (TypeError, ValueError, Exception) as e:
            raise ValueError("{0} : msgpack marshal error: {1}".format(self.Name, e))

    # -----------------------------------------------------------------------------------------------

    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        try:
            return msgpackUnpackb(data, raw=False)
        except (TypeError, ValueError, Exception) as e:
            raise ValueError("{0} : msgpack unmarshal error: {1}".format(self.Name, e))


# -----------------------------------------------------------------------------------------------


def new_json_serializer() -> Serializer:
    """Factory method for JSON serializer."""
    return JSONSerializer()


# -----------------------------------------------------------------------------------------------


def new_bin_serializer() -> Serializer:
    """Factory method for MessagePack serializer."""
    return BinSerializer()
