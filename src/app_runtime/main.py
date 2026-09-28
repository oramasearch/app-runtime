"""Runtime command-line entrypoint."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping

import uvicorn

from app_runtime.errors import AppRuntimeError, ConfigurationError
from app_runtime.frameworks import build_application
from app_runtime.loader import load_app
from app_runtime.streamlit_proxy import StreamlitProcess, build_streamlit_proxy


def main() -> int:
    try:
        return run(os.environ)
    except AppRuntimeError as error:
        print(f"app-runtime: {error}", file=sys.stderr)
        return 1


def run(environment: Mapping[str, str]) -> int:
    loaded = load_app(environment)
    streamlit: StreamlitProcess | None = None
    try:
        os.chdir(loaded.root)
        port = public_port(environment, loaded.config.port)
        if loaded.config.framework == "streamlit":
            streamlit = StreamlitProcess(loaded.root, loaded.config.entrypoint)
            streamlit.start()
            application = build_streamlit_proxy(streamlit)
        else:
            application = build_application(loaded.root, loaded.config)
        uvicorn.run(application, host="0.0.0.0", port=port)
    finally:
        if streamlit is not None:
            streamlit.stop()
        os.chdir("/tmp")
        shutil.rmtree(loaded.root)
    return 0


def public_port(environment: Mapping[str, str], manifest_port: int) -> int:
    value = environment.get("APP_PORT")
    if value is None or not value.strip():
        return manifest_port
    try:
        port = int(value)
    except ValueError as error:
        raise ConfigurationError("APP_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ConfigurationError("APP_PORT must be from 1 through 65535")
    return port


if __name__ == "__main__":
    raise SystemExit(main())
