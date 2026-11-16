# SPDX-License-Identifier: MIT

"""Parse and validate an App's app.toml manifest."""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

from app_runtime.errors import ConfigurationError, DependencyError

BAKED_DEPENDENCIES = frozenset(
    {
        "fastapi",
        "httpx",
        "jinja2",
        "numpy",
        "pandas",
        "plotly",
        "pydantic",
        "streamlit",
        "uvicorn",
    }
)
FRAMEWORKS = frozenset({"fastapi", "static", "streamlit"})
SERVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class BindingRequirements:
    zetta: bool = False
    services: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppConfig:
    name: str
    framework: str
    entrypoint: str
    port: int
    dependencies: tuple[str, ...] = ()
    bindings: BindingRequirements = field(default_factory=BindingRequirements)

    @classmethod
    def read(cls, manifest: Path) -> AppConfig:
        try:
            with manifest.open("rb") as stream:
                values = tomllib.load(stream)
        except FileNotFoundError as error:
            raise ConfigurationError("app.toml is required at the App root") from error
        except tomllib.TOMLDecodeError as error:
            raise ConfigurationError(f"app.toml is not valid TOML: {error}") from error
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> AppConfig:
        name = required_string(values, "name")
        framework = required_string(values, "framework").lower()
        if framework not in FRAMEWORKS:
            choices = ", ".join(sorted(FRAMEWORKS))
            raise ConfigurationError(f"framework must be one of: {choices}")
        entrypoint = required_string(values, "entrypoint")
        port = values.get("port", 8080)
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ConfigurationError("port must be an integer from 1 through 65535")
        dependencies = parse_dependencies(values.get("dependencies", []))
        bindings = parse_bindings(values.get("bindings", {}))
        return cls(
            name=name,
            framework=framework,
            entrypoint=entrypoint,
            port=port,
            dependencies=dependencies,
            bindings=bindings,
        )

    def validate_dependencies(self) -> None:
        refused: list[str] = []
        mismatched: list[str] = []
        for declared in self.dependencies:
            try:
                requirement = Requirement(declared)
            except InvalidRequirement as error:
                raise ConfigurationError(f"invalid dependency {declared!r}: {error}") from error
            normalized = requirement.name.lower().replace("_", "-")
            if requirement.url:
                refused.append(declared)
                continue
            if requirement.marker and not requirement.marker.evaluate():
                continue
            try:
                # Baked packages, or ones lake's build_app installed into this image's venv.
                installed = importlib.metadata.version(normalized)
            except importlib.metadata.PackageNotFoundError:
                refused.append(declared)
                continue
            if requirement.specifier and installed not in requirement.specifier:
                mismatched.append(f"{declared} (runtime has {installed})")
        if refused or mismatched:
            details = []
            if refused:
                details.append("not installed in this runtime: " + ", ".join(refused))
            if mismatched:
                details.append("version not satisfied: " + ", ".join(mismatched))
            raise DependencyError(
                "; ".join(details) + ". Use App image mode for custom dependencies."
            )


def required_string(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{key} must be a non-empty string")
    return value.strip()


def parse_dependencies(value: Any) -> tuple[str, ...]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(item.strip() for item in value if item.strip())
    if isinstance(value, dict):
        dependencies = []
        for name, constraint in value.items():
            if not isinstance(name, str) or not isinstance(constraint, str):
                raise ConfigurationError("dependencies must map package names to constraints")
            if constraint in ("", "*"):
                dependencies.append(name)
            elif constraint.startswith(("<", ">", "=", "!", "~")):
                dependencies.append(f"{name}{constraint}")
            else:
                dependencies.append(f"{name}=={constraint}")
        return tuple(dependencies)
    raise ConfigurationError("dependencies must be an array of requirement strings or a table")


def parse_bindings(value: Any) -> BindingRequirements:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        zetta = "zetta" in value
        services = tuple(
            item.removeprefix("service:")
            for item in value
            if item.startswith("service:") and item.removeprefix("service:")
        )
        unknown = [
            item
            for item in value
            if item != "zetta" and not item.startswith("service:")
        ]
        if unknown:
            raise ConfigurationError("unknown bindings: " + ", ".join(unknown))
        validate_service_names(services)
        return BindingRequirements(zetta=zetta, services=services)
    if isinstance(value, dict):
        zetta = value.get("zetta", False)
        services = value.get("services", [])
        if not isinstance(zetta, bool):
            raise ConfigurationError("bindings.zetta must be true or false")
        if not isinstance(services, list) or not all(
            isinstance(item, str) and item for item in services
        ):
            raise ConfigurationError("bindings.services must be an array of service names")
        unknown = set(value) - {"zetta", "services"}
        if unknown:
            raise ConfigurationError("unknown binding keys: " + ", ".join(sorted(unknown)))
        parsed_services = tuple(services)
        validate_service_names(parsed_services)
        return BindingRequirements(zetta=zetta, services=parsed_services)
    raise ConfigurationError("bindings must be a table or an array")


def validate_service_names(services: tuple[str, ...]) -> None:
    invalid = [name for name in services if not SERVICE_NAME.fullmatch(name)]
    if invalid:
        raise ConfigurationError("invalid Service binding names: " + ", ".join(invalid))
