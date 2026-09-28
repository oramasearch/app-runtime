# Loading an App

The runtime reads an App only from a lake repository at a pinned revision. The operator supplies
either the combined source variable:

```text
APP_SOURCE=<lake_url>|<repository>|<revision>|<path>
```

or `LAKE_URL`, `APP_REPOSITORY`, `APP_REVISION` and optional `APP_PATH` separately. `APP_TOKEN` is
the bearer token used for lake's `repository_tree` and `repository_file` capabilities. A missing
revision is refused. The files are written below `/tmp`, so the image's root filesystem can remain
read-only.

The selected path must contain `app.toml`:

```toml
name = "sales-dashboard"
framework = "fastapi" # fastapi, streamlit or static
entrypoint = "dashboard:app"
port = 8080
dependencies = ["fastapi>=0.116", "pandas"]

[bindings]
zetta = true
services = ["reporting-postgres"]
```

Dependencies may instead be a TOML table mapping package names to versions or constraints. The
runtime installs nothing after startup. An App may declare only the packages already baked into
the image: `fastapi==0.116.1`, `uvicorn==0.35.0`, `streamlit==1.48.1`, `pandas==2.3.1`,
`numpy==2.3.2`, `plotly==6.2.0`, `httpx==0.28.1`, `pydantic==2.11.7` and `jinja2==3.1.6`. A package
outside that set, a direct URL, or an incompatible version is refused with guidance to use App
image mode.

`bindings` can also be written as `bindings = ["zetta", "service:reporting-postgres"]`. Required
binding files are checked before the App is served.
