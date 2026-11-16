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
Thank you for helping. This document says how to build and test app-runtime, how a change gets in,
and the one thing every contributor does first: sign the Contributor License
Agreement.

## Before you start

- For a bug, open an issue with what you did, what you expected and what happened, and the
  version or commit.
- For a larger change (a new feature, a new dependency, a change to an interface), open an issue
  first so the approach can be agreed before you write it.
- **Security issues are never reported in a public issue.** See [SECURITY.md](SECURITY.md): write
  to **security@orama.com**.

## Build and test

You need Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```sh
uv sync          # creates .venv with the locked dependencies, including the test tools
uv run pytest    # the whole test suite
```

The container image is built from the `Dockerfile`:

```sh
docker build -t app-runtime:local .
```

## Making a change

1. Fork the repository and branch from `dev`. `main` is the last release; it moves only when a
   release is cut.
2. Keep one change per pull request, with the tests that prove it. A change in behavior updates
   the documentation it touches in the same pull request.
3. Write commit messages in the [Conventional Commits](https://www.conventionalcommits.org/) form,
   for example `fix(api): reject an empty name`.
4. Sign the Contributor License Agreement before your first pull request is merged (next section).
5. Open the pull request against `dev`. Start its description with what changes, why, and how.

A maintainer reviews it. Pull requests are merged with a merge commit, so every commit you make
stays in the history.

## Contributor License Agreement

app-runtime is owned by OramaSearch, Inc. Every contributor signs the
[Contributor License Agreement](CLA.md) (CLA) once, before their first pull request is merged. Under
it you assign the copyright in your contributions to OramaSearch, Inc., you keep a licence to use
your own contributions for any purpose, and you grant a patent licence for them. The project is
published under the MIT License (see [LICENSE](LICENSE)).

When you open your first pull request, a bot comments on it with a link to the agreement. Sign
there with your GitHub account; it covers all your later contributions to projects of OramaSearch,
Inc. If you contribute as part of your job, your employer signs too: write to
**opensource@orama.com** for the entity agreement.

## License headers

Every source file starts with the line `SPDX-License-Identifier: MIT`, in that file's comment
syntax, for example `// SPDX-License-Identifier: MIT`. Add it to a new file yourself, or run:

```sh
python3 tools/spdx-headers.py           # adds the line where it is missing
python3 tools/spdx-headers.py --check   # lists files without it
```

Code copied from another project keeps its own license header and is listed in
[THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES). Say so in the pull request, with where it came from
and its license; it must be compatible with the MIT License.

## Code of conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Report unacceptable
behavior to **conduct@orama.com**.
