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


def write_identity_app(root: Path, module: str) -> None:
    (root / f"{module}.py").write_text(
        "from fastapi import FastAPI, Request\n"
        "from orama_app import current_user\n"
        "app = FastAPI()\n"
        "@app.get('/me')\n"
        "async def me():\n"
        "    return current_user()\n"
        "@app.get('/headers')\n"
        "async def headers(request: Request):\n"
        "    return sorted(name for name in request.headers.keys() if name.startswith('x-'))\n"
    )


FORGED_IDENTITY_HEADERS = (
    {"X-Orama-User": "forged-member"},
    {"X-Orama-User": json.dumps({"id": "forged-member"})},
    {"X-Orama-User-Id": "forged-member", "X-Orama-User-Email": "forged@example.test"},
    {"X-Auth-Request-User": "forged-member", "X-Auth-Request-Email": "forged@example.test"},
)


@pytest.mark.anyio
async def test_current_user_is_request_local_for_fastapi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A Lake-protected app: ingress-nginx sets X-Orama-User from Lake's forward-auth answer.
    monkeypatch.setenv("APP_AUTH", "lake")
    write_identity_app(tmp_path, "current_user_app")
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
        bare = await client.get("/me", headers={"X-Orama-User": "member-1"})
        assert bare.json() == {"id": "member-1"}
        assert (await client.get("/me")).json() is None
    assert current_user() is None


@pytest.mark.anyio
@pytest.mark.parametrize("auth", ["public", None, "", "Lake", " lake"])
async def test_a_public_app_never_trusts_client_identity_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth: str | None,
) -> None:
    # No forward auth stands in front of a public app (or an app whose operator does not say
    # it is Lake-protected), so every identity header reached the pod from the client.
    if auth is None:
        monkeypatch.delenv("APP_AUTH", raising=False)
    else:
        monkeypatch.setenv("APP_AUTH", auth)
    module = "public_identity_app_" + ("unset" if auth is None else str(abs(hash(auth))))
    write_identity_app(tmp_path, module)
    application = build_fastapi_application(tmp_path, f"{module}:app")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://runtime",
    ) as client:
        for headers in FORGED_IDENTITY_HEADERS:
            assert (await client.get("/me", headers=headers)).json() is None
            # The forged headers are removed before App code can read them itself.
            assert (await client.get("/headers", headers=headers)).json() == []


@pytest.mark.anyio
async def test_a_lake_protected_app_ignores_the_unsigned_fallback_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ingress-nginx replaces only X-Orama-User and X-Orama-Space; nothing replaces these.
    monkeypatch.setenv("APP_AUTH", "lake")
    write_identity_app(tmp_path, "lake_fallback_identity_app")
    application = build_fastapi_application(tmp_path, "lake_fallback_identity_app:app")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://runtime",
    ) as client:
        for headers in FORGED_IDENTITY_HEADERS[2:]:
            assert (await client.get("/me", headers=headers)).json() is None
            assert (await client.get("/headers", headers=headers)).json() == []
        kept = await client.get(
            "/headers",
            headers={
                "X-Orama-User": "member-1",
                "X-Orama-Space": "space-1",
                "X-Auth-Request-User": "forged-member",
            },
        )
        assert kept.json() == ["x-orama-space", "x-orama-user"]


def test_user_from_headers_reads_only_forward_auth_on_a_lake_protected_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orama_app.user import user_from_headers

    monkeypatch.setenv("APP_AUTH", "public")
    assert user_from_headers({"x-orama-user": "forged-member"}) is None
    monkeypatch.delenv("APP_AUTH")
    assert user_from_headers({"x-orama-user": "forged-member"}) is None
    monkeypatch.setenv("APP_AUTH", "lake")
    assert user_from_headers({"x-auth-request-user": "forged-member"}) is None
    assert user_from_headers({"x-orama-user-id": "forged-member"}) is None
    assert user_from_headers({"x-orama-user": "member-1"}) == {"id": "member-1"}


def test_orama_current_user_is_for_local_development_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORAMA_CURRENT_USER", json.dumps({"id": "local-dev"}))
    monkeypatch.delenv("APP_AUTH", raising=False)
    assert current_user() == {"id": "local-dev"}
    for auth in ("public", "lake"):
        monkeypatch.setenv("APP_AUTH", auth)
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


def test_lake_forward_auth_sends_a_bare_member_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from orama_app.user import user_from_headers

    monkeypatch.setenv("APP_AUTH", "lake")
    assert user_from_headers({"x-orama-user": "accc9652-3ade-4c07-8047-b0fa3c909f90"}) == {
        "id": "accc9652-3ade-4c07-8047-b0fa3c909f90"
    }
    assert user_from_headers({"x-orama-user": '{"id": "u1", "email": "a@example.test"}'}) == {
        "id": "u1",
        "email": "a@example.test",
    }


# The operator writes this exact file (orama-operator internal/controller/testdata/
# app-binding-zetta.json, checked byte for byte by its contract test). lake#1205: the operator
# used to write the bare token, which stopped every App with workspace data at startup.
OPERATOR_ZETTA_BINDING = Path(__file__).parent / "fixtures" / "operator-zetta-binding.json"


def test_the_operators_zetta_binding_reaches_the_workspace_through_lake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "zetta").write_bytes(OPERATOR_ZETTA_BINDING.read_bytes())
    monkeypatch.setenv("ORAMA_BINDINGS_DIR", str(tmp_path))
    validate_bindings(BindingRequirements(zetta=True))
    requests: list[httpx.Request] = []

    def fake_lake(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "value": {"datasets": []}})

    with zetta(_transport=httpx.MockTransport(fake_lake)) as workspace:
        assert workspace.datasets() == []
    assert len(requests) == 1
    assert requests[0].url.host == "lake-dev.lake-dev.svc.cluster.local"
    assert requests[0].url.path == (
        "/w/11111111-2222-4333-8444-555555555555"
        "/workspaces/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0/zetta/v1/list_datasets"
    )
    assert requests[0].headers["authorization"] == (
        "Bearer 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )


def test_a_bare_token_binding_stops_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "zetta").write_text("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("ORAMA_BINDINGS_DIR", str(tmp_path))
    with pytest.raises(ConfigurationError, match="binding is not valid JSON"):
        validate_bindings(BindingRequirements(zetta=True))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("auth", "forwarded"),
    [("public", []), ("lake", ["x-orama-space", "x-orama-user"])],
)
async def test_the_streamlit_proxy_forwards_only_trusted_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
    auth: str,
    forwarded: list[str],
) -> None:
    from app_runtime import streamlit_proxy

    monkeypatch.setenv("APP_AUTH", auth)
    seen: list[list[str]] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(sorted(name for name in request.headers.keys() if name.startswith("x-")))
        return httpx.Response(200, text="ok")

    real_client = httpx.AsyncClient

    def client_with_fake_transport(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(record)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(streamlit_proxy.httpx, "AsyncClient", client_with_fake_transport)

    class FakeProcess:
        http_url = "http://streamlit.invalid"
        process = None

    application = streamlit_proxy.build_streamlit_proxy(FakeProcess())  # type: ignore[arg-type]
    async with real_client(
        transport=httpx.ASGITransport(app=application),
        base_url="http://runtime",
    ) as client:
        response = await client.get(
            "/page",
            headers={
                "X-Orama-User": "member-1",
                "X-Orama-Space": "space-1",
                "X-Orama-User-Id": "forged-member",
                "X-Auth-Request-User": "forged-member",
            },
        )
    assert response.status_code == 200
    assert seen == [forwarded]
