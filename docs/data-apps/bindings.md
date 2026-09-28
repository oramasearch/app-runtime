# `orama_app` and bindings

The operator mounts JSON files below `/var/run/orama/bindings`. Apps declare the ones they require
in `app.toml`; startup stops before importing App code if a required file is missing or invalid.
`ORAMA_BINDINGS_DIR` changes the root for local development and tests.

## Workspace Zetta

`/var/run/orama/bindings/zetta` contains the scoped, read-only workspace credential:

```json
{"lake_url":"https://lake.example","customer_id":"customer-id","token":"scoped-token"}
```

The token goes only to lake's workspace proxy at
`/workspaces/<customer_id>/zetta/v1/<capability>`. Apps use it through the helper:

```python
from orama_app import zetta

with zetta() as workspace:
    datasets = workspace.datasets()
    rows = workspace.sql('SELECT * FROM "sales"."orders" LIMIT 100')["rows"]
    runs = workspace.runs()
    models = workspace.models()
    risks = workspace.score("churn-model", dataset_path="sales.accounts", top_k=10)
```

The binding may use `zetta_url` or `base_url` instead of `lake_url` plus `customer_id` when the
operator has already formed the filtered Zetta base URL. `sql`, `datasets`, `runs`, `models` and
`score` are read calls. `read(capability, **arguments)` exposes another read capability allowed by
the scoped token. A failed envelope raises `ZettaError` with lake's code and message.

## Services

Each expected Service has one JSON object at `/var/run/orama/bindings/services/<name>`. The object
is returned unchanged, so the Service controller can provide connection-specific fields:

```python
from orama_app import service

postgres_url = service("reporting-postgres")["url"]
kafka_brokers = service("events-kafka")["brokers"]
```

Service names accept letters, numbers, dots, underscores and hyphens; paths cannot escape the
binding directory.

## Signed-in user

For `auth: lake`, the auth proxy passes either `X-Orama-User` as a JSON object or
`X-Orama-User-Id` with optional `X-Orama-User-Email` and `X-Orama-User-Name`. The runtime keeps the
identity request-local for FastAPI and forwards the headers to Streamlit:

```python
from orama_app import current_user

user = current_user()  # {"id": ..., "email": ..., "name": ...}, or None
```

`X-Auth-Request-User` and `X-Auth-Request-Email` are also accepted. `ORAMA_CURRENT_USER` supplies
the same JSON object for local development only.

The [data dashboard example](../../examples/data-dashboard/) lists the workspace datasets and
previews the selected dataset with governed SQL.
