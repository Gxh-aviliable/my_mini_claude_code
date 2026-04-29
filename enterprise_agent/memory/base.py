from abc import ABC, abstractmethod
from typing import Dict, Any


class MemoryBase(ABC):
    """Abstract base class for memory storage"""

    @abstractmethod
    async def store(self, key: str, data: Dict[str, Any]) -> None:
        """Store data with given key"""
        pass

    @abstractmethod
    async def retrieve(self, key: str) -> Dict[str, Any]:
        """Retrieve data by key"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete data by key"""
        pass