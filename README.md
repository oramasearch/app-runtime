# app-runtime

The Python base runtime that runs lake Apps. It loads an App from a lake repository at a pinned
revision, validates `app.toml` without installing anything, and serves FastAPI, Streamlit or static
content.

Released: [v0.1.3](docs/releases/v0.1.3.md). Its image is published as `oramasearch/app-runtime` on Docker Hub.

## Source and manifest

The operator sets `APP_SOURCE=<lake_url>|<repository>|<revision>|<path>` or the equivalent
`LAKE_URL`, `APP_REPOSITORY`, `APP_REVISION` and `APP_PATH` variables, plus the read-only lake bearer
token in `APP_TOKEN`. The runtime reads the pinned tree through lake's `repository_tree` and
`repository_file` capabilities and materializes it below `/tmp`.

Every App has an `app.toml` containing its `name`, `framework`, `entrypoint`, `port`, declared
`dependencies` and expected `bindings`. See [Loading an App](docs/loading/apps.md) for the schema,
the exact environment contract and startup refusals.

The pinned baked set is FastAPI, Uvicorn, Streamlit, pandas, NumPy, Plotly, HTTPX, Pydantic and
Jinja. Apps needing anything else use image mode: lake's `build_app` installs the extra
packages into this image's `/app/.venv`, and startup accepts any declared dependency that is
installed and satisfies its specifier (URL requirements are always refused).

## Frameworks and health

FastAPI Apps name a `module:object`, Streamlit Apps name a Python script and static Apps name a
content directory. Every framework serves `/healthz` and `/readyz` on the public port. `APP_PORT`
overrides the manifest port; the image defaults it to 8080. Streamlit runs on loopback behind the
runtime so its application traffic and the common health contract share one public port. The runtime
accepts Streamlit's WebSocket only from a page on the host it was sent to, and gives Streamlit its own
loopback origin, so Streamlit never looks up its external IP (a blocking call a pod without internet
egress waits on). It relays Streamlit's messages whatever their size, so a page with a large table or
chart keeps updating. Details
are in [Frameworks and health](docs/runtime/frameworks.md). The downloaded App root remains on
Python's module path while it is served, including for imports performed inside request handlers.

The Python 3.12 image runs as UID 10001 and stores App code below `/tmp`, making it compatible with
a read-only root filesystem and writable `/tmp`.

## Bindings and data Apps

The operator mounts binding JSON at `/var/run/orama/bindings/zetta` and
`/var/run/orama/bindings/services/<name>`. The `orama_app` package provides `zetta()` for governed
workspace SQL, datasets, runs, models and scoring; `service(name)` for Service connection fields;
and request-local `current_user()`, which is the signed-in member only on a Lake-protected App
(`APP_AUTH=lake`, set by the operator) and `None` on a public one; identity headers a client could
forge are removed before App code sees the request. See [`orama_app` and bindings](docs/data-apps/bindings.md)
for file shapes and examples.

[`examples/data-dashboard`](examples/data-dashboard/) is a Streamlit App that lists datasets from
a fakeable Zetta binding and previews workspace rows.
