"""Email delivery adapter placeholder."""

from typing import Any

from .base import BaseTool


class EmailDeliveryTool(BaseTool):
    """Deliver a user-approved trip summary."""

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("Configure an email provider.")
