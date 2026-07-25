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
COPY src ./src
COPY scripts ./scripts
COPY supabase ./supabase

FROM base AS dev

COPY .github ./.github
COPY docker ./docker
COPY docs ./docs
COPY frontend ./frontend
COPY tests ./tests
COPY .env.example AGENTS.md compose.yaml ./
COPY contracts/openapi.json ./contracts/openapi.json
RUN uv sync --frozen --group dev --extra api --extra llm --extra streamlit --extra worker

CMD ["pytest"]

FROM base AS runtime

ENV WEREWOLF_LOG_DIR=.werewolf-agent/logs \
    WEREWOLF_LOG_FILE_NAME=werewolf-agent.jsonl \
    WEREWOLF_LOG_OUTPUT=file \
    WEREWOLF_LOG_RETENTION_DAYS=14 \
    WEREWOLF_LOG_THIRD_PARTY_LEVEL=WARNING

RUN uv sync --frozen --no-dev --extra api --extra llm --extra streamlit --extra worker
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app

USER app

CMD ["werewolf-agent-worker", "run"]
