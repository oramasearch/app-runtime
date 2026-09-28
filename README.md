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
