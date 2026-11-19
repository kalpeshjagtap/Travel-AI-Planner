"""Base interface for external service tools."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """A typed boundary around one external or local capability."""

    @abstractmethod
    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        """Invoke the capability and return normalized structured data."""
