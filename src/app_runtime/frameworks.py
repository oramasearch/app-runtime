"""Build the public server for each supported App framework."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app_runtime.config import AppConfig
from app_runtime.errors import ConfigurationError
from app_runtime.user_context import CurrentUserMiddleware


def build_application(root: Path, config: AppConfig) -> FastAPI:
    if config.framework == "fastapi":
        return build_fastapi_application(root, config.entrypoint)
    if config.framework == "static":
        return build_static_application(root, config.entrypoint)
    raise ConfigurationError("Streamlit uses its own process and proxy")


def build_fastapi_application(root: Path, entrypoint: str) -> FastAPI:
    module_name, separator, object_name = entrypoint.partition(":")
    if not separator or not module_name or not object_name:
        raise ConfigurationError("a FastAPI entrypoint must be module:object")
    ensure_local_module(root, module_name)
    sys.path.insert(0, str(root))
    try:
        module = importlib.import_module(module_name)
    except Exception as error:
        raise ConfigurationError(f"cannot import FastAPI module {module_name}: {error}") from error
    finally:
        sys.path.remove(str(root))
    try:
        user_application: Any = getattr(module, object_name)
    except AttributeError as error:
        raise ConfigurationError(
            f"FastAPI entrypoint {entrypoint} does not exist"
        ) from error
    if not callable(user_application):
        raise ConfigurationError(f"FastAPI entrypoint {entrypoint} is not an ASGI application")
    application = health_application()
    application.mount("/", user_application)
    return application


def build_static_application(root: Path, entrypoint: str) -> FastAPI:
    content = confined_path(root, entrypoint)
    if not content.is_dir():
        raise ConfigurationError(f"static entrypoint is not a directory: {entrypoint}")
    application = health_application()
    application.mount("/", StaticFiles(directory=content, html=True))
    return application


def health_application() -> FastAPI:
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(CurrentUserMiddleware)

    @application.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz", include_in_schema=False)
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return application


def ensure_local_module(root: Path, module_name: str) -> None:
    if any(not part.isidentifier() for part in module_name.split(".")):
        raise ConfigurationError(f"invalid module in entrypoint: {module_name}")
    module_path = root.joinpath(*module_name.split("."))
    if not module_path.with_suffix(".py").is_file() and not (
        module_path / "__init__.py"
    ).is_file():
        raise ConfigurationError(f"entrypoint module is not in the App: {module_name}")


def confined_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ConfigurationError(f"entrypoint escapes the App root: {relative}") from error
    return candidate
