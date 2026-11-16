# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app_runtime import ConfigurationError, DependencyError, LoadError, load_app
from app_runtime.config import AppConfig
from app_runtime.source import AppSource


def test_combined_source_requires_pinned_revision() -> None:
    with pytest.raises(ConfigurationError, match="pinned revision"):
        AppSource.from_environment(
            {"APP_SOURCE": "https://lake.example|repository-id||apps/dashboard"}
        )


def test_loads_app_from_fake_lake_at_selected_path() -> None:
    requests: list[tuple[str, dict[str, list[str]]]] = []
    files = {
        "unrelated.txt": "ignored",
        "apps/dashboard/app.toml": manifest(),
        "apps/dashboard/dashboard.py": "app = object()\n",
    }

    def fake_lake(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        requests.append((request.url.path, query))
        assert request.headers["authorization"] == "Bearer read-token"
        if request.url.path == "/v1/repository_tree":
            items = [{"path": path, "kind": "file"} for path in files]
            return httpx.Response(200, json={"ok": True, "value": {"items": items}})
        path = query["path"][0]
        return httpx.Response(
            200,
            json={"ok": True, "value": {"contents": files[path]}},
        )

    loaded = load_app(
        {
            "APP_SOURCE": "https://lake.example|repository-id|commit-sha|apps/dashboard",
            "APP_TOKEN": "read-token",
        },
        transport=httpx.MockTransport(fake_lake),
    )
    try:
        assert loaded.config.name == "Dashboard"
        assert (loaded.root / "dashboard.py").read_text() == "app = object()\n"
        assert not (loaded.root / "unrelated.txt").exists()
        assert requests[0][1]["ref"] == ["commit-sha"]
    finally:
        shutil.rmtree(loaded.root)


def test_disallowed_dependency_refuses_with_image_mode_guidance(tmp_path: Path) -> None:
    config = AppConfig.from_mapping(
        {
            "name": "custom",
            "framework": "fastapi",
            "entrypoint": "app:app",
            "dependencies": ["scikit-learn"],
        }
    )
    with pytest.raises(DependencyError, match="Use App image mode"):
        config.validate_dependencies()


def test_installed_dependency_outside_the_baked_set_is_accepted() -> None:
    # An image from lake's build_app has the App's extra packages installed in /app/.venv.
    config = AppConfig.from_mapping(
        {
            "name": "custom",
            "framework": "fastapi",
            "entrypoint": "app:app",
            "dependencies": ["packaging"],
        }
    )
    config.validate_dependencies()


def test_repository_path_escape_is_refused() -> None:
    def fake_lake(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True, "value": {"items": [{"path": "../secret"}]}},
        )

    with pytest.raises(LoadError, match="escapes"):
        load_app(
            {
                "APP_SOURCE": "https://lake.example|repository-id|commit-sha|",
                "APP_TOKEN": "read-token",
            },
            transport=httpx.MockTransport(fake_lake),
        )


def manifest() -> str:
    return """\
name = "Dashboard"
framework = "fastapi"
entrypoint = "dashboard:app"
port = 8080
dependencies = ["fastapi>=0.116"]
"""


def test_image_mode_loads_the_app_baked_into_the_image(tmp_path: Path) -> None:
    # lake's build_app copies the App's files into /app; the operator sets no source in image mode.
    (tmp_path / "app.toml").write_text(
        'name = "notes"\nframework = "fastapi"\nentrypoint = "main:app"\nport = 8080\n'
    )
    (tmp_path / "main.py").write_text("app = object()\n")
    loaded = load_app({"APP_ROOT": str(tmp_path)})
    assert loaded.baked is True
    assert loaded.source is None
    assert loaded.root == tmp_path
    assert loaded.config.entrypoint == "main:app"


def test_without_source_or_baked_app_the_source_error_remains(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="LAKE_URL is required"):
        load_app({"APP_ROOT": str(tmp_path)})


def test_repository_file_bytes_come_from_content_base64_unchanged() -> None:
    import base64

    from app_runtime.lake import decode_contents

    source = 'st.title("\U0001f465 Customer Insights") · café\n'.encode()
    # What Lake answers: exact bytes in content_base64, and a lossy text form in contents (2026-10-26).
    body = {
        "content_base64": base64.b64encode(source).decode(),
        "contents": 'st.title("\\xF0\\x9F\\x91\\xA5 Customer Insights") \\xC2\\xB7 caf\\xC3\\xA9\n',
    }
    assert decode_contents(body, "app.py") == source
    assert decode_contents({"contents": "plain"}, "app.py") == b"plain"
