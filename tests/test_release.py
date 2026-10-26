from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_release_version_is_documented() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    notes = ROOT / "docs" / "releases" / f"v{version}.md"
    assert notes.is_file(), f"no release notes for v{version}"
    assert f"v{version}" in (ROOT / "docs" / "releases" / "README.md").read_text()
