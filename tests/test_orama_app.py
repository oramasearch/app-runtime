from __future__ import annotations

import importlib
import json
import runpy
from pathlib import Path
from typing import Any

import httpx
import pytest

from app_runtime.bindings import validate_bindings
from app_runtime.config import BindingRequirements
from app_runtime.errors import ConfigurationError
from app_runtime.frameworks import build_fastapi_application
from orama_app import BindingError, current_user, service, zetta

zetta_module = importlib.import_module("orama_app.zetta")


def test_zetta_client_reads_bound_workspace_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_binding(
        tmp_path / "zetta",
        {
            "lake_url": "https://lake.example",
            "customer_id": "customer-id",
            "token": "scoped-token",
        },
    )
    monkeypatch.setenv("ORAMA_BINDINGS_DIR", str(tmp_path))
    requests: list[httpx.Request] = []

    def fake_workspace(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        capability = request.url.path.rsplit("/", 1)[-1]
        values = {
            "list_datasets": {"datasets": [{"database": "sales", "name": "orders"}]},
            "list_runs": {"runs": [{"id": "run-1"}]},
            "list_models": {"models": [{"id": "model-1"}]},
            "sql": {"columns": ["count"], "rows": [{"count": 3}], "messages": []},
            "score": {"ranked": [{"entity": 7, "risk": 0.9}]},
        }
        return httpx.Response(200, json={"ok": True, "value": values[capability]})

    with zetta(_transport=httpx.MockTransport(fake_workspace)) as workspace:
        assert workspace.datasets()[0]["name"] == "orders"
        assert workspace.runs()[0]["id"] == "run-1"
        assert workspace.models()[0]["id"] == "model-1"
        assert workspace.sql("SELECT 3")["rows"] == [{"count": 3}]
        assert workspace.score("model-1", rows=[{"value": 4}])["ranked"][0]["entity"] == 7
    assert all(
        request.url.path.startswith("/workspaces/customer-id/zetta/v1/")
        for request in requests
    )
    assert all(request.headers["authorization"] == "Bearer scoped-token" for request in requests)


def test_service_returns_connection_object_and_rejects_path_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_binding(tmp_path / "services" / "postgres", {"url": "postgresql://database/app"})
    monkeypatch.setenv("ORAMA_BINDINGS_DIR", str(tmp_path))
    assert service("postgres")["url"] == "postgresql://database/app"
    with pytest.raises(BindingError, match="invalid Service"):
        service("../secret")


def test_expected_binding_is_required_before_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORAMA_BINDINGS_DIR", str(tmp_path))
    with pytest.raises(ConfigurationError, match="required binding is unavailable"):
        validate_bindings(BindingRequirements(zetta=True))


@pytest.mark.anyio
async def test_current_user_is_request_local_for_fastapi(tmp_path: Path) -> None:
    (tmp_path / "current_user_app.py").write_text(
        "from fastapi import FastAPI\n"
        "from orama_app import current_user\n"
        "app = FastAPI()\n"
        "@app.get('/me')\n"
        "async def me():\n"
        "    return current_user()\n"
    )
    application = build_fastapi_application(tmp_path, "current_user_app:app")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://runtime",
    ) as client:
        response = await client.get(
            "/me",
            headers={"X-Orama-User": json.dumps({"id": "user-1", "email": "u@example.com"})},
        )
        assert response.json() == {"id": "user-1", "email": "u@example.com"}
        assert (await client.get("/me")).json() is None
    assert current_user() is None


def test_data_dashboard_uses_a_fake_zetta_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_binding(
        tmp_path / "zetta",
        {"zetta_url": "https://zetta.example", "token": "scoped-token"},
    )
    monkeypatch.setenv("ORAMA_BINDINGS_DIR", str(tmp_path))
    real_client = httpx.Client

    def fake_workspace(request: httpx.Request) -> httpx.Response:
        capability = request.url.path.rsplit("/", 1)[-1]
        if capability == "list_datasets":
            value = {
                "datasets": [
                    {
                        "database": "sales",
                        "name": "orders",
                        "rows": 1,
                        "size_bytes": 24,
                    }
                ]
            }
        else:
            value = {"columns": ["id"], "rows": [{"id": 42}], "messages": []}
        return httpx.Response(200, json={"ok": True, "value": value})

    def client_with_fake_transport(**arguments: Any) -> httpx.Client:
        arguments["transport"] = httpx.MockTransport(fake_workspace)
        return real_client(**arguments)

    monkeypatch.setattr(zetta_module.httpx, "Client", client_with_fake_transport)
    dashboard = runpy.run_path("examples/data-dashboard/dashboard.py", run_name="dashboard_test")
    fake_streamlit = FakeStreamlit()
    dashboard["main"].__globals__["st"] = fake_streamlit
    dashboard["main"]()
    assert fake_streamlit.frames[-1] == [{"id": 42}]


def write_binding(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class FakeStreamlit:
    def __init__(self) -> None:
        self.frames: list[Any] = []

    def title(self, _: str) -> None:
        pass

    def caption(self, _: str) -> None:
        pass

    def info(self, _: str) -> None:
        pass

    def dataframe(self, value: Any, **_: Any) -> None:
        self.frames.append(value)

    def selectbox(self, _: str, choices: list[str]) -> str:
        return choices[0]


def test_lake_forward_auth_sends_a_bare_member_id() -> None:
    from orama_app.user import user_from_headers

    assert user_from_headers({"x-orama-user": "accc9652-3ade-4c07-8047-b0fa3c909f90"}) == {
        "id": "accc9652-3ade-4c07-8047-b0fa3c909f90"
    }
    assert user_from_headers({"x-orama-user": '{"id": "u1", "email": "a@example.test"}'}) == {
        "id": "u1",
        "email": "a@example.test",
    }
