# SPDX-License-Identifier: MIT

"""Load operator-provided connection bindings from files."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from orama_app.zetta import ZettaClient

DEFAULT_BINDINGS_DIRECTORY = Path("/var/run/orama/bindings")
SERVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BindingError(RuntimeError):
    """A required binding is missing or invalid."""


def bindings_directory() -> Path:
    override = os.environ.get("ORAMA_BINDINGS_DIR")
    return Path(override) if override else DEFAULT_BINDINGS_DIRECTORY


def zetta(*, _transport: httpx.BaseTransport | None = None) -> ZettaClient:
    """Return a lake-proxied client for the bound workspace."""
    binding = read_binding(bindings_directory() / "zetta")
    return ZettaClient.from_binding(binding, transport=_transport)


def service(name: str) -> dict[str, Any]:
    """Return the connection information for one bound Service."""
    if not SERVICE_NAME.fullmatch(name):
        raise BindingError(f"invalid Service binding name: {name!r}")
    return read_binding(bindings_directory() / "services" / name)


def read_binding(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise BindingError(f"binding is not available: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise BindingError(f"binding is not valid JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise BindingError(f"binding must contain a JSON object: {path}")
    return value
