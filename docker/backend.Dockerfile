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

CMD ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS runtime

ENV WEREWOLF_DJANGO_DEBUG=false \
    WEREWOLF_DJANGO_SQLITE_PATH=/data/db.sqlite3 \
    PORT=8000

RUN uv sync --frozen --no-dev --extra api
RUN python backend/manage.py collectstatic --noinput
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:%s/api/health/' % port, timeout=5).read()" || exit 1

CMD ["sh", "-c", "gunicorn werewolf_agent.interfaces.api.config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --access-logfile - --error-logfile -"]
