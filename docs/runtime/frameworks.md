# Frameworks and health

Every framework exposes `GET /healthz` for liveness and `GET /readyz` for readiness on the App's
public port. Both return HTTP 200 only after the App has loaded. `APP_PORT` overrides `app.toml`'s
`port`; otherwise the manifest port is used. The image defaults `APP_PORT` to 8080.

Entrypoints depend on the framework:

- FastAPI uses `module:object`. The module must be part of the downloaded App. The runtime imports
  the ASGI object, keeps the App root on Python's module path for handler-time imports, mounts it
  below the two probe routes and serves the result with Uvicorn.
- Streamlit uses a Python file such as `dashboard.py`. Streamlit listens only on an ephemeral
  loopback port. The public Uvicorn process owns the health routes and proxies HTTP and WebSocket
  traffic to Streamlit. Readiness checks Streamlit's own health endpoint.
  - A WebSocket is relayed only when its `Origin` names the host it was sent to (the app's public host);
    any other origin is closed with 1008. Streamlit receives its own loopback address as the origin.
    Its own check does not know the public host, and checking an unknown host makes it look up its
    external IP with a blocking call to `checkip.amazonaws.com`. A workspace pod has no internet egress,
    so every page stalled while the lookup timed out, and the stream got 403.
  - Streamlit starts with `--browser.serverAddress=127.0.0.1` for the same reason.
- Static uses a directory such as `public`. The runtime serves it with HTML index support below
  the probe routes.

The image uses Python 3.12, runs as UID 10001, writes downloaded source only below `/tmp`, disables
bytecode writes and uses `/tmp` as `HOME`. It is compatible with a read-only root filesystem and a
writable `/tmp` mount. The private image is built and pushed by the cluster BuildKit after review;
workstations do not build or publish it.
