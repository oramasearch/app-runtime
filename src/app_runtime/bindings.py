"""Validate an App's declared bindings before it starts serving."""

from __future__ import annotations

from app_runtime.config import BindingRequirements
from app_runtime.errors import ConfigurationError
from orama_app.bindings import BindingError, service
from orama_app.bindings import zetta as bound_zetta


def validate_bindings(requirements: BindingRequirements) -> None:
    try:
        if requirements.zetta:
            client = bound_zetta()
            client.close()
        for name in requirements.services:
            service(name)
    except (BindingError, RuntimeError) as error:
        raise ConfigurationError(f"required binding is unavailable: {error}") from error
