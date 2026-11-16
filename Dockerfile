# syntax=docker/dockerfile:1
# Bases are pinned by their multi-platform index digest (lake#1003); a new base is a reviewed
# change of the digest, not a moved tag.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN useradd --uid 10001 --no-create-home app
COPY --from=build /app/.venv /app/.venv
ENV APP_PORT=8080 \
    HOME=/tmp \
    PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 8080
ENTRYPOINT ["app-runtime"]
