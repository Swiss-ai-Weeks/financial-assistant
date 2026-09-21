"""
Advisory assistant over one ClaimGraph view.

It explains what is on screen and can move the view. It can
never add evidence, relations or review decisions: the graph
stays the product of the investigation pipeline.
"""

from .context import validate_context
from .service import CopilotService, requested_route, validate_reply

__all__ = [
    "CopilotService",
    "requested_route",
    "validate_context",
    "validate_reply",
]
