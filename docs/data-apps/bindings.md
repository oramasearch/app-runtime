# `orama_app` and bindings

The operator mounts JSON files below `/var/run/orama/bindings`. Apps declare the ones they require
in `app.toml`; startup stops before importing App code if a required file is missing or invalid.
`ORAMA_BINDINGS_DIR` changes the root for local development and tests.

## Workspace Zetta

`/var/run/orama/bindings/zetta` contains the scoped, read-only workspace credential:

```json
{"lake_url":"https://lake.example","customer_id":"customer-id","token":"scoped-token"}
```

The orama-operator writes exactly this shape, with `lake_url` set to the app's in-cluster
`LAKE_URL` (`http://lake-<lake>.<namespace>.svc.cluster.local:80/w/<workspace id>`). Its bytes are a
contract: `tests/fixtures/operator-zetta-binding.json` is a copy of the operator's
`internal/controller/testdata/app-binding-zetta.json`, and both repositories test it. A bare token in
this file is not JSON and stops startup with *"binding is not valid JSON"* (lake#1205).

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

`current_user()` returns the signed-in Lake member only on a **Lake-protected** App (`auth: lake`),
and `None` on every other request:

```python
from orama_app import current_user

user = current_user()  # {"id": ...} on a Lake-protected App, or None
```

Where the identity comes from, and why it can be trusted:

- The operator sets `APP_AUTH` in the pod from the LakeApp's `spec.auth` (`lake` or `public`), and an
  App's own environment cannot override it.
- On a Lake-protected App, ingress-nginx asks Lake's forward auth about every request and sets
  `X-Orama-User` (the member's id) and `X-Orama-Space` (the workspace) from Lake's answer. Those two
  headers are named in the Ingress's `auth-response-headers`, so ingress-nginx **replaces** any copy
  the client sent, or removes it when Lake sends none. The App's network policy admits only
  ingress-nginx and its Lake, so no request reaches the pod around the ingress.
- With `APP_AUTH=lake` the runtime reads `X-Orama-User` (a bare id, or a JSON object) and nothing
  else. With `APP_AUTH=public`, or no `APP_AUTH`, it reads no identity header at all: no proxy sets
  them on a public App, so whatever arrives was written by the client.

The runtime also **removes** identity headers a client could have forged before the App sees the
request, so App code that reads raw headers is protected as well. On every App that is
`X-Orama-User-Id`, `X-Orama-User-Email`, `X-Orama-User-Name` and every `X-Auth-Request-*` header (no
proxy in front of an App sets them; earlier runtimes accepted them as identity, which let a client
choose who it was). On an App that is not Lake-protected it is also `X-Orama-User` and
`X-Orama-Space`. Streamlit receives the request after this, through the runtime's proxy.

An App in image mode that does not run on this runtime gets none of this: it must not treat these
headers as identity unless it is Lake-protected.

`ORAMA_CURRENT_USER` supplies the same JSON object for local development only: it is read only when
`APP_AUTH` is not set, which is never the case for an App the operator runs.

The [data dashboard example](../../examples/data-dashboard/) lists the workspace datasets and
previews the selected dataset with governed SQL.
