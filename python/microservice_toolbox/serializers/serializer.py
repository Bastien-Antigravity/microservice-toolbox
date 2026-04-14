from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

T = TypeVar('T')

class ISerializer(ABC):
    """
    ISerializer manages transforming generic objects to bytes and vice-versa.
    """
    
    @abstractmethod
    def marshal(self, data: Any) -> bytes:
        """
        Transforms data into a byte representation.
        """
        pass
    
    @abstractmethod
    def unmarshal(self, data: bytes, cls: Type[T]) -> T:
        """
        Transforms a byte representation back into an object of type cls.
        """
        pass
