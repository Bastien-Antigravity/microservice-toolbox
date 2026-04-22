#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Defines the abstract interface for serialization providers within the ecosystem.
ISerializer manages transforming generic objects to bytes and vice-versa.

DATA FLOW:
1. Data structures are converted to bytes via marshal.
2. Bytes are converted back to data structures via unmarshal.

KEY PARAMETERS:
- data: The object to be serialized.
- cls: The target type for deserialization.
"""

from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

T = TypeVar("T")

# -----------------------------------------------------------------------------------------------


class ISerializer(ABC):
    """
    ISerializer manages transforming generic objects to bytes and vice-versa.
    """

    Name = "ISerializer"

    # -----------------------------------------------------------------------------------------------

    @abstractmethod
    def marshal(self, data: Any) -> bytes:
        """
        Transforms data into a byte representation.
        """
        pass

    # -----------------------------------------------------------------------------------------------

    @abstractmethod
    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        """
        Transforms a byte representation back into an object of type cls.
        """
        pass
