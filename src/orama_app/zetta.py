"""A small client for the workspace's filtered Zetta REST capabilities."""

from __future__ import annotations

import json
from typing import Any, Self

import httpx


class ZettaError(RuntimeError):
    """lake or Zetta refused a workspace operation."""


class ZettaClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            timeout=timeout,
        )

    @classmethod
    def from_binding(
        cls,
        binding: dict[str, Any],
        transport: httpx.BaseTransport | None = None,
    ) -> ZettaClient:
        token = binding.get("token")
        if not isinstance(token, str) or not token:
            raise ZettaError("zetta binding requires token")
        direct_url = binding.get("zetta_url")
        if direct_url is None:
            direct_url = binding.get("base_url")
        if direct_url is not None:
            if not isinstance(direct_url, str) or not direct_url:
                raise ZettaError("zetta binding base URL must be a non-empty string")
            base_url = direct_url
        else:
            lake_url = binding.get("lake_url") or binding.get("url")
            customer_id = binding.get("customer_id")
            if not isinstance(lake_url, str) or not lake_url:
                raise ZettaError("zetta binding requires lake_url")
            if not isinstance(customer_id, str) or not customer_id:
                raise ZettaError("zetta binding requires customer_id")
            base_url = f"{lake_url.rstrip('/')}/workspaces/{customer_id}/zetta"
        return cls(base_url, token, transport=transport)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def read(self, capability: str, **arguments: Any) -> Any:
        parameters = {
            name: value if isinstance(value, str) else json.dumps(value)
            for name, value in arguments.items()
            if value is not None
        }
        try:
            response = self.client.get(f"/v1/{capability}", params=parameters)
        except httpx.HTTPError as error:
            raise ZettaError(f"{capability} failed: {type(error).__name__}: {error}") from error
        return response_value(capability, response)

    def sql(
        self,
        statement: str,
        *,
        database: str | None = None,
        intent: str | None = None,
    ) -> dict[str, Any]:
        return self.read("sql", statement=statement, database=database, intent=intent)

    def datasets(self, *, intent: str | None = None) -> list[dict[str, Any]]:
        value = self.read("list_datasets", intent=intent)
        return require_list(value, "datasets", "list_datasets")

    def runs(self, *, intent: str | None = None) -> list[dict[str, Any]]:
        value = self.read("list_runs", intent=intent)
        return require_list(value, "runs", "list_runs")

    def models(self, *, intent: str | None = None) -> list[dict[str, Any]]:
        value = self.read("list_models", intent=intent)
        return require_list(value, "models", "list_models")

    def score(
        self,
        model: str,
        *,
        dataset_path: str | None = None,
        rows: list[dict[str, Any]] | None = None,
        entities: list[int] | None = None,
        dataset: dict[str, Any] | None = None,
        top_k: int | None = None,
        intent: str | None = None,
    ) -> dict[str, Any]:
        return self.read(
            "score",
            model=model,
            dataset_path=dataset_path,
            rows=rows,
            entities=entities,
            dataset=dataset,
            top_k=top_k,
            intent=intent,
        )


def response_value(capability: str, response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError as error:
        raise ZettaError(
            f"{capability} returned HTTP {response.status_code} without JSON"
        ) from error
    if isinstance(body, dict) and body.get("ok") is True:
        return body.get("value")
    detail = body.get("error") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        code = detail.get("code", response.status_code)
        message = detail.get("message", "")
        raise ZettaError(f"{capability} failed: {code}: {message}")
    raise ZettaError(f"{capability} failed: HTTP {response.status_code}")


def require_list(value: Any, key: str, capability: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise ZettaError(f"{capability} returned an invalid {key} value")
    return value[key]

