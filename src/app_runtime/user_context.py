"""Install lake-auth identity in request-local App context."""

from __future__ import annotations

from typing import Any

from orama_app.user import (
    reset_current_user,
    set_current_user,
    untrusted_identity_header,
    user_from_headers,
)


class CurrentUserMiddleware:
    """Expose Lake's forward-auth identity and drop identity headers a client could forge.

    Forged identity headers are removed from the request before the App, or the Streamlit
    process behind the runtime, sees it, so App code that reads raw headers is protected too.
    """

    def __init__(self, application: Any) -> None:
        self.application = application

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.application(scope, receive, send)
            return
        kept: list[tuple[bytes, bytes]] = []
        headers: dict[str, str] = {}
        for name, value in scope.get("headers", []):
            lowered = name.decode("latin-1").lower()
            if untrusted_identity_header(lowered):
                continue
            kept.append((name, value))
            headers[lowered] = value.decode("latin-1")
        token = set_current_user(user_from_headers(headers))
        try:
            await self.application({**scope, "headers": kept}, receive, send)
        finally:
            reset_current_user(token)
