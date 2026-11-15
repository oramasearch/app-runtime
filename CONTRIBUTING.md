# Contributing to app-runtime

app-runtime is the Python base runtime that runs lake Apps: it loads an App's code from a lake
repository at a pinned revision and serves it (FastAPI, Streamlit or static), with the `orama_app`
helper library for data Apps. [`README.md`](README.md) and [`docs/`](docs/) describe the contract.

## Build and test

```sh
uv sync
uv run pytest
```

Say in your pull request which tests you ran.

## Pull requests

- Branch from `dev` and open the pull request against `dev`; `main` holds the last release.
- Update `README.md` and any page under `docs/` in the same pull request as the code.
- `tests/fixtures/operator-zetta-binding.json` is a byte-for-byte copy of the Orama operator's
  `internal/controller/testdata/app-binding-zetta.json`; change both together.
- Reference the issue a pull request works on with `Refs #N`.
- Do not run a formatter over files you did not otherwise change.

## Security

Report a vulnerability privately, as [`SECURITY.md`](SECURITY.md) describes, never in a public issue.
