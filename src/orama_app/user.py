# SPDX-License-Identifier: MIT

"""Per-request lake-auth identity exposed to App code."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import Any

_CURRENT_USER: ContextVar[dict[str, Any] | None] = ContextVar(
    "orama_current_user",
    default=None,
)

# The operator sets APP_AUTH from the LakeApp's spec.auth. Only on a Lake-protected App does
# ingress-nginx call Lake's forward auth and set these headers from Lake's answer, replacing (or,
# when Lake sends none, removing) whatever the client sent. Every other identity header reaches the
# pod exactly as the client wrote it.
LAKE_AUTH = "lake"
FORWARD_AUTH_HEADERS = frozenset({"x-orama-user", "x-orama-space"})
# Headers earlier runtimes read as identity. No proxy in front of an App sets them, so they are
# client-controlled on every App and are removed before App code sees the request.
UNSIGNED_IDENTITY_HEADERS = frozenset(
    {
        "x-orama-user-id",
        "x-orama-user-email",
        "x-orama-user-name",
    }
)
UNSIGNED_IDENTITY_PREFIXES = ("x-auth-request-",)


def app_auth() -> str | None:
    """Return the App's auth mode as the operator set it, or None outside the operator."""
    return os.environ.get("APP_AUTH")


def forward_auth_trusted() -> bool:
    """Whether X-Orama-User and X-Orama-Space were set by Lake's forward auth for this App.

    Exactly ``lake``, as the operator writes it; any other value is treated as public.
    """
    return app_auth() == LAKE_AUTH


def untrusted_identity_header(name: str) -> bool:
    """Whether a (lower-case) request header is identity the client could have forged."""
    if name in UNSIGNED_IDENTITY_HEADERS or name.startswith(UNSIGNED_IDENTITY_PREFIXES):
        return True
    return name in FORWARD_AUTH_HEADERS and not forward_auth_trusted()


def current_user() -> dict[str, Any] | None:
    """Return the signed-in lake member for this request on a Lake-protected App, else None."""
    user = _CURRENT_USER.get()
    if user is not None:
        return dict(user)
    streamlit_user = streamlit_current_user()
    if streamlit_user is not None:
        return streamlit_user
    configured = os.environ.get("ORAMA_CURRENT_USER")
    if configured and app_auth() is None:
        # Local development only: an App the operator runs always has APP_AUTH.
        return decode_user(configured)
    return None


def user_from_headers(headers: Mapping[str, str]) -> dict[str, Any] | None:
    """Read Lake's forward-auth identity; None unless the App is Lake-protected."""
    if not forward_auth_trusted():
        return None
    serialized = headers.get("x-orama-user")
    if not serialized or not serialized.strip():
        return None
    # Lake's forward-auth sends the member's id; a JSON object is also accepted.
    if not serialized.lstrip().startswith("{"):
        return {"id": serialized.strip()}
    return decode_user(serialized)


def decode_user(serialized: str) -> dict[str, Any]:
    try:
        user = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise RuntimeError("lake auth supplied invalid user JSON") from error
    if not isinstance(user, dict):
        raise TypeError("lake auth user must be a JSON object")
    return user


def set_current_user(user: dict[str, Any] | None) -> Token[dict[str, Any] | None]:
    return _CURRENT_USER.set(user)


def reset_current_user(token: Token[dict[str, Any] | None]) -> None:
    _CURRENT_USER.reset(token)


def streamlit_current_user() -> dict[str, Any] | None:
    try:
        import streamlit as st

        headers = {name.lower(): value for name, value in st.context.headers.items()}
    except (AttributeError, RuntimeError):
        return None
    return user_from_headers(headers)
