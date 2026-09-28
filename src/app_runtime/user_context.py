"""Install lake-auth identity in request-local App context."""

from __future__ import annotations

from typing import Any

from orama_app.user import reset_current_user, set_current_user, user_from_headers


class CurrentUserMiddleware:
    def __init__(self, application: Any) -> None:
        self.application = application

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        token = set_current_user(user_from_headers(headers))
        try:
            await self.application(scope, receive, send)
        finally:
            reset_current_user(token)
