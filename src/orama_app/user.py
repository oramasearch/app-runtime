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


def current_user() -> dict[str, Any] | None:
    """Return the signed-in lake member for this request, when supplied."""
    user = _CURRENT_USER.get()
    if user is not None:
        return dict(user)
    streamlit_user = streamlit_current_user()
    if streamlit_user is not None:
        return streamlit_user
    configured = os.environ.get("ORAMA_CURRENT_USER")
    if configured:
        return decode_user(configured)
    return None


def user_from_headers(headers: Mapping[str, str]) -> dict[str, Any] | None:
    serialized = headers.get("x-orama-user")
    if serialized:
        # Lake's forward-auth sends the member's id; a JSON object is also accepted.
        if not serialized.lstrip().startswith("{"):
            return {"id": serialized.strip()}
        return decode_user(serialized)
    user_id = headers.get("x-orama-user-id") or headers.get("x-auth-request-user")
    if not user_id:
        return None
    user = {"id": user_id}
    email = headers.get("x-orama-user-email") or headers.get("x-auth-request-email")
    name = headers.get("x-orama-user-name")
    if email:
        user["email"] = email
    if name:
        user["name"] = name
    return user


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
