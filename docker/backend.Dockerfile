# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend

FROM base AS dev

RUN uv sync --frozen --group dev --extra api

EXPOSE 8000

CMD ["uvicorn", "werewolf_agent.interface.entrypoint.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime

ENV WEREWOLF_API_DEBUG=false \
    WEREWOLF_SQLITE_PATH=/data/db.sqlite3 \
    PORT=8000

RUN uv sync --frozen --no-dev --extra api
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % port, timeout=5).read()" || exit 1

CMD ["sh", "-c", "uvicorn werewolf_agent.interface.entrypoint.api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
