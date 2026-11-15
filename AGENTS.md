# AGENTS.md: working in app-runtime

The Python base runtime that runs lake Apps: it loads an app's code from a lake repository at a pinned revision and serves it (FastAPI, Streamlit or static), with the orama_app helper library for data apps. The design is under [`docs/`](docs/README.md).

## Build and test
```sh
uv sync
uv run pytest
```
Say in the pull request which tests you ran.

## Non-negotiables
- **No AI attribution** anywhere: no Co-Authored-By, no "Generated with", no mention of AI in commits, PRs, tags or release notes.
- **No time or size estimates.** Do the work; report concrete results.
- **Docs in the same change:** update README.md (and any docs page) with every code change.
- **Feature branch + PR against `dev`.** Never push to `main`; it holds the last release. PRs reference their issue with `Refs #N`, never an auto-close keyword. Merge commits, never squash.
- Never run a formatter over files you did not otherwise change.
- Never write the word "seam": name the mechanism (interface, extension point, boundary).
- Report vulnerabilities privately, as `SECURITY.md` describes.
