from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app_runtime.config import AppConfig
from app_runtime.frameworks import build_application
from app_runtime.loader import LoadedApp, load_app
from app_runtime.source import AppSource
from app_runtime.streamlit_proxy import StreamlitProcess, build_streamlit_proxy


@pytest.mark.anyio
async def test_fastapi_app_from_fake_lake_passes_health_checks() -> None:
    loaded = fake_lake_app(
        """\
name = "API"
framework = "fastapi"
entrypoint = "app:app"
port = 8080
dependencies = ["fastapi"]
""",
        """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/hello")
async def hello():
    from greeting import message
    return {"hello": message}
""",
        "app.py",
        extra_files={"greeting.py": "message = 'world'\n"},
    )
    try:
        application = build_application(loaded.root, loaded.config)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://runtime",
        ) as client:
            assert (await client.get("/healthz")).json() == {"status": "ok"}
            assert (await client.get("/readyz")).json() == {"status": "ready"}
            assert (await client.get("/hello")).json() == {"hello": "world"}
    finally:
        shutil.rmtree(loaded.root)


@pytest.mark.anyio
async def test_streamlit_app_from_fake_lake_passes_health_checks() -> None:
    loaded = fake_lake_app(
        """\
name = "Dashboard"
framework = "streamlit"
entrypoint = "dashboard.py"
port = 8080
dependencies = ["streamlit"]
""",
        """\
import streamlit as st
st.title("Dashboard")
""",
        "dashboard.py",
    )
    process = StreamlitProcess(loaded.root, loaded.config.entrypoint)
    try:
        process.start()
        application = build_streamlit_proxy(process)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://runtime",
        ) as client:
            assert (await client.get("/healthz")).status_code == 200
            assert (await client.get("/readyz")).status_code == 200
            page = await client.get("/")
            assert page.status_code == 200
            assert "streamlit" in page.text.lower()
    finally:
        process.stop()
        shutil.rmtree(loaded.root)


@pytest.mark.anyio
async def test_static_app_has_health_checks_and_content(tmp_path: Path) -> None:
    content = tmp_path / "public"
    content.mkdir()
    (content / "index.html").write_text("<h1>Static App</h1>")
    loaded = LoadedApp(
        root=tmp_path,
        config=AppConfig.from_mapping(
            {
                "name": "Static",
                "framework": "static",
                "entrypoint": "public",
            }
        ),
        source=AppSource("https://lake.example", "repository", "commit"),
    )
    application = build_application(loaded.root, loaded.config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://runtime",
    ) as client:
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.get("/readyz")).status_code == 200
        assert "Static App" in (await client.get("/")).text


def fake_lake_app(
    manifest: str,
    source: str,
    source_path: str,
    extra_files: dict[str, str] | None = None,
) -> LoadedApp:
    files = {
        "app/app.toml": manifest,
        f"app/{source_path}": source,
    }
    for path, contents in (extra_files or {}).items():
        files[f"app/{path}"] = contents

    def fake_lake(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        if request.url.path == "/v1/repository_tree":
            items = [{"path": path, "kind": "file"} for path in files]
            return httpx.Response(200, json={"ok": True, "value": {"items": items}})
        path = query["path"][0]
        return httpx.Response(
            200,
            json={"ok": True, "value": {"contents": files[path]}},
        )

    return load_app(
        {
            "APP_SOURCE": "https://lake.example|repository|commit|app",
            "APP_TOKEN": "token",
        },
        transport=httpx.MockTransport(fake_lake),
    )
