"""Route dependencies and helpers

Provides clean access to application state without Law of Demeter violations.
"""
from fastapi import Request

from app_state import AppState


def get_app_state(request: Request) -> AppState:
    """Get AppState from request

    Encapsulates the request.app.state.app_state chain to fix
    Law of Demeter violation in all routes.

    Usage:
        @router.get("/example")
        async def example(request: Request):
            app_state = get_app_state(request)
            # Use app_state directly
    """
    return request.app.state.app_state
