"""Read an App definition through lake's repository REST capabilities."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Self

import httpx

from app_runtime.errors import LoadError
from app_runtime.source import AppSource


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    contents: bytes


class LakeRepository:
    def __init__(
        self,
        source: AppSource,
        token: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.source = source
        self.client = httpx.Client(
            base_url=source.lake_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def files(self) -> list[RepositoryFile]:
        tree = self._read(
            "repository_tree",
            id=self.source.repository,
            ref=self.source.revision,
        )
        items = tree.get("items", []) if isinstance(tree, dict) else tree
        if not isinstance(items, list):
            raise LoadError("repository_tree returned an invalid item list")
        files = []
        for item in items:
            if not isinstance(item, dict) or item.get("kind") not in (None, "file", "blob"):
                continue
            repository_path = item.get("path", "")
            app_path = relative_app_path(repository_path, self.source.path)
            if app_path is None:
                continue
            body = self._read(
                "repository_file",
                id=self.source.repository,
                ref=self.source.revision,
                path=repository_path,
            )
            files.append(RepositoryFile(app_path, decode_contents(body, repository_path)))
        return files

    def _read(self, capability: str, **arguments: str) -> Any:
        try:
            response = self.client.get(f"/v1/{capability}", params=arguments)
        except httpx.HTTPError as error:
            raise LoadError(f"{capability} failed: {type(error).__name__}: {error}") from error
        try:
            body = response.json()
        except ValueError as error:
            raise LoadError(f"{capability} returned HTTP {response.status_code} without JSON") from error
        if isinstance(body, dict) and body.get("ok") is True:
            return body.get("value")
        detail = body.get("error") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            code = detail.get("code", response.status_code)
            message = detail.get("message", "")
            raise LoadError(f"{capability} failed: {code}: {message}")
        raise LoadError(f"{capability} failed: HTTP {response.status_code}")


def relative_app_path(repository_path: Any, root: str) -> str | None:
    if not isinstance(repository_path, str) or not repository_path:
        raise LoadError("repository_tree returned an invalid file path")
    path = PurePosixPath(repository_path)
    if path.is_absolute() or ".." in path.parts:
        raise LoadError(f"repository path escapes the App root: {repository_path}")
    root_path = PurePosixPath(root.strip("/")) if root else PurePosixPath()
    try:
        relative = path.relative_to(root_path)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return relative.as_posix()


def decode_contents(body: Any, path: str) -> bytes:
    if not isinstance(body, dict):
        raise LoadError(f"repository_file returned an invalid value for {path}")
    # The file's exact bytes. Lake's `contents` text writes every non-ASCII byte as literal `\xNN` text, so an App's
    # emoji or accent arrived as `\xF0\x9F...` on the page (2026-10-26); `content_base64` carries the bytes unchanged.
    exact = body.get("content_base64")
    if isinstance(exact, str):
        try:
            return base64.b64decode(exact, validate=True)
        except ValueError as error:
            raise LoadError(f"repository_file returned invalid base64 for {path}") from error
    contents = body.get("contents")
    if not isinstance(contents, str):
        raise LoadError(f"repository_file returned no contents for {path}")
    if body.get("encoding") == "base64":
        try:
            return base64.b64decode(contents, validate=True)
        except ValueError as error:
            raise LoadError(f"repository_file returned invalid base64 for {path}") from error
    return contents.encode()
