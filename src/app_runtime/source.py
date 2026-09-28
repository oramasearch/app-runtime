"""The operator-facing environment contract for an App source."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from app_runtime.errors import ConfigurationError


@dataclass(frozen=True)
class AppSource:
    """A path in a lake repository at an immutable revision."""

    lake_url: str
    repository: str
    revision: str
    path: str = ""

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> AppSource:
        values = os.environ if environment is None else environment
        combined = values.get("APP_SOURCE", "").strip()
        if combined:
            parts = combined.split("|", 3)
            if len(parts) != 4:
                raise ConfigurationError(
                    "APP_SOURCE must be <lake_url>|<repository>|<revision>|<path>"
                )
            source = cls(
                lake_url=parts[0].strip(),
                repository=parts[1].strip(),
                revision=parts[2].strip(),
                path=parts[3].strip(),
            )
        else:
            source = cls(
                lake_url=values.get("LAKE_URL", "").strip(),
                repository=values.get("APP_REPOSITORY", "").strip(),
                revision=values.get("APP_REVISION", "").strip(),
                path=values.get("APP_PATH", "").strip(),
            )
        source.validate()
        return source

    def validate(self) -> None:
        if not self.lake_url:
            raise ConfigurationError("LAKE_URL is required")
        if not self.repository:
            raise ConfigurationError("APP_REPOSITORY is required")
        if not self.revision:
            raise ConfigurationError("APP_REVISION must be a pinned revision")
        if any(part == ".." for part in self.path.split("/")):
            raise ConfigurationError("APP_PATH must stay inside the repository")
