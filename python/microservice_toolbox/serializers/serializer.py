#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Defines the abstract interface for serialization providers within the ecosystem.
Serializer manages transforming generic objects to bytes and vice-versa.

DATA FLOW:
1. Data structures are converted to bytes via marshal.
2. Bytes are converted back to data structures via unmarshal.

KEY PARAMETERS:
- data: The object to be serialized.
- cls: The target type for deserialization.
"""

from abc import ABC as abcABC, abstractmethod as abcAbstractmethod
from typing import Any as typeAny, Type as typeType, TypeVar as typeTypeVar

T = typeTypeVar("T")

# -----------------------------------------------------------------------------------------------


class Serializer(abcABC):
    """
    Serializer manages transforming generic objects to bytes and vice-versa.
    """

    Name = "Serializer"

    # -----------------------------------------------------------------------------------------------

    @abcAbstractmethod
    def marshal(self, data: typeAny) -> bytes:
        """
        Transforms data into a byte representation.
        """
        pass

    # -----------------------------------------------------------------------------------------------

    @abcAbstractmethod
    def unmarshal(self, data: bytes, cls: typeType[T]) -> T:
        """
        Transforms a byte representation back into an object of type cls.
        """
        pass

