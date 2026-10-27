"""Run Streamlit privately and expose it with the runtime health contract."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from app_runtime.errors import ConfigurationError, LoadError
from app_runtime.frameworks import confined_path
from app_runtime.user_context import CurrentUserMiddleware

HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class StreamlitProcess:
    def __init__(self, root: Path, entrypoint: str) -> None:
        script = confined_path(root, entrypoint)
        if not script.is_file() or script.suffix != ".py":
            raise ConfigurationError(f"Streamlit entrypoint is not a Python file: {entrypoint}")
        self.root = root
        self.script = script
        self.port = available_port()
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def http_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def websocket_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def start(self, timeout: float = 30.0) -> None:
        environment = os.environ.copy()
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            f"{self.root}{os.pathsep}{existing_path}" if existing_path else str(self.root)
        )
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(self.script),
            "--server.address=127.0.0.1",
            f"--server.port={self.port}",
            "--server.headless=true",
            # A manually set address means Streamlit never looks up an external IP. The lookup is a blocking HTTP call
            # to checkip.amazonaws.com that a workspace pod (no internet egress) waits on for ten seconds.
            "--browser.serverAddress=127.0.0.1",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        self.process = subprocess.Popen(command, cwd=self.root, env=environment)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise LoadError(f"Streamlit exited with status {self.process.returncode}")
            try:
                response = httpx.get(f"{self.http_url}/_stcore/health", timeout=0.5)
                if response.is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        self.stop()
        raise LoadError("Streamlit did not become ready")

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def build_streamlit_proxy(process: StreamlitProcess) -> FastAPI:
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(CurrentUserMiddleware)

    @application.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        if process.process is None or process.process.poll() is not None:
            return Response(status_code=503, content="Streamlit is not running")
        return {"status": "ok"}

    @application.get("/readyz", include_in_schema=False)
    async def ready() -> Response:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{process.http_url}/_stcore/health",
                    timeout=1.0,
                )
        except httpx.HTTPError:
            return Response(status_code=503, content="Streamlit is not ready")
        status = 200 if response.is_success else 503
        return Response(status_code=status, content=response.content)

    @application.api_route(
        "/{path:path}",
        methods=["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
        include_in_schema=False,
    )
    async def proxy_http(request: Request, path: str) -> Response:
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "host"
        }
        async with httpx.AsyncClient(follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                f"{process.http_url}/{path}",
                params=request.query_params,
                headers=headers,
                content=await request.body(),
            )
        response_headers = {
            name: value
            for name, value in upstream.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS
        }
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    @application.websocket("/{path:path}")
    async def proxy_websocket(websocket: WebSocket, path: str) -> None:
        query = f"?{websocket.url.query}" if websocket.url.query else ""
        if not same_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
            await websocket.close(code=1008)
            return
        requested = websocket.headers.get("sec-websocket-protocol", "")
        subprotocols = [item.strip() for item in requested.split(",") if item.strip()]
        forwarded_headers = {
            name: value
            for name, value in websocket.headers.items()
            if name.lower()
            not in {
                "connection",
                "host",
                "origin",
                "sec-websocket-extensions",
                "sec-websocket-key",
                "sec-websocket-protocol",
                "sec-websocket-version",
                "upgrade",
            }
        }
        try:
            async with connect(
                f"{process.websocket_url}/{path}{query}",
                # The browser's origin is checked above. Streamlit sees its own address instead: its own check does not
                # know the app's public host, and checking an unknown host makes it look up its external IP (above).
                additional_headers={**forwarded_headers, "Origin": process.http_url},
                subprotocols=subprotocols or None,
                # No size limit on what Streamlit sends (app-runtime#26). Streamlit sends a whole page update as one
                # message: a large table or chart is more than websockets' default 1 MiB, and refusing it closes the
                # stream, so the page never updates again. The sender is the App's own Streamlit on loopback, which
                # already limits its messages (server.maxMessageSize, 200 MB by default).
                max_size=None,
            ) as upstream:
                await websocket.accept(subprotocol=upstream.subprotocol)
                await relay_websocket(websocket, upstream)
        except (ConnectionClosed, InvalidHandshake, OSError):
            with suppress(RuntimeError):
                await websocket.close(code=1011)

    return application


def same_origin(origin: str | None, host: str | None) -> bool:
    """Whether a WebSocket's Origin is the host it was sent to; a request without Origin is not from a browser page."""
    if origin is None:
        return True
    if not host:
        return False
    return urlsplit(origin).netloc.lower() == host.lower()


async def relay_websocket(websocket: WebSocket, upstream: Any) -> None:
    async def to_upstream() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is None:
                data = message.get("text", "")
            await upstream.send(data)

    async def to_client() -> None:
        async for message in upstream:
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                await websocket.send_text(message)

    tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        with suppress(WebSocketDisconnect, ConnectionClosed):
            task.result()


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])
