# app-runtime

The Python base runtime that runs lake Apps. It loads an App from a lake repository at a pinned
revision, validates `app.toml` without installing anything, and serves FastAPI, Streamlit or static
content. Epic: oramasearch/lake#297.

Private. Its image is published **private** as `oramasearch/app-runtime` on Docker Hub.

## Source and manifest

The operator sets `APP_SOURCE=<lake_url>|<repository>|<revision>|<path>` or the equivalent
`LAKE_URL`, `APP_REPOSITORY`, `APP_REVISION` and `APP_PATH` variables, plus the read-only lake bearer
token in `APP_TOKEN`. The runtime reads the pinned tree through lake's `repository_tree` and
`repository_file` capabilities and materializes it below `/tmp`.

Every App has an `app.toml` containing its `name`, `framework`, `entrypoint`, `port`, declared
`dependencies` and expected `bindings`. See [Loading an App](docs/loading/apps.md) for the schema,
the exact environment contract and startup refusals.

The pinned baked set is FastAPI, Uvicorn, Streamlit, pandas, NumPy, Plotly, HTTPX, Pydantic and
Jinja. Apps needing anything else use image mode.

## Frameworks and health

FastAPI Apps name a `module:object`, Streamlit Apps name a Python script and static Apps name a
content directory. Every framework serves `/healthz` and `/readyz` on the public port. `APP_PORT`
overrides the manifest port; the image defaults it to 8080. Streamlit runs on loopback behind the
runtime so its application traffic and the common health contract share one public port. Details
are in [Frameworks and health](docs/runtime/frameworks.md).

The Python 3.12 image runs as UID 10001 and stores App code below `/tmp`, making it compatible with
a read-only root filesystem and writable `/tmp`.
