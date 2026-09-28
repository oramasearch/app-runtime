"""Materialize and validate an App before importing any of its code."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import httpx

from app_runtime.config import AppConfig
from app_runtime.errors import ConfigurationError, LoadError
from app_runtime.lake import LakeRepository
from app_runtime.source import AppSource


@dataclass(frozen=True)
class LoadedApp:
    root: Path
    config: AppConfig
    source: AppSource


def load_app(
    environment: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> LoadedApp:
    values = os.environ if environment is None else environment
    source = AppSource.from_environment(values)
    token = values.get("APP_TOKEN", "").strip()
    if not token:
        raise ConfigurationError("APP_TOKEN is required")
    target = Path(tempfile.mkdtemp(prefix="orama-app-"))
    try:
        with LakeRepository(source, token, transport=transport) as repository:
            files = repository.files()
        if not files:
            raise LoadError("the App path contains no files")
        for item in files:
            destination = target.joinpath(*item.path.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(item.contents)
        config = AppConfig.read(target / "app.toml")
        config.validate_dependencies()
    except Exception:
        remove_materialized_app(target)
        raise
    return LoadedApp(root=target, config=config, source=source)


def remove_materialized_app(root: Path) -> None:
    for child in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    root.rmdir()

