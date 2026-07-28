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

FROM base AS runtime-dependencies

RUN uv sync --frozen --no-dev --extra api --extra llm --extra streamlit --extra worker --no-install-project

FROM base AS dev-dependencies

RUN uv sync --frozen --group dev --extra api --extra llm --extra streamlit --extra worker --no-install-project

FROM dev-dependencies AS dev

COPY src ./src
COPY scripts ./scripts
COPY supabase ./supabase
COPY .streamlit ./.streamlit
COPY .github ./.github
COPY docker ./docker
COPY docs ./docs
COPY tests ./tests
COPY .env.example AGENTS.md compose.yaml ./
COPY contracts/openapi.json ./contracts/openapi.json
RUN uv sync --frozen --group dev --extra api --extra llm --extra streamlit --extra worker

CMD ["pytest"]

FROM runtime-dependencies AS runtime

COPY src ./src
COPY scripts/__init__.py ./scripts/__init__.py
COPY scripts/_infra ./scripts/_infra
COPY scripts/supabase ./scripts/supabase
COPY supabase ./supabase
COPY .streamlit ./.streamlit

ENV WEREWOLF_LOG_DIR=.werewolf-agent/logs/application \
    WEREWOLF_LOG_FILE_NAME=werewolf-agent.jsonl \
    WEREWOLF_LOG_OUTPUT=stdout \
    WEREWOLF_LOG_FILE_MAX_MIB=10 \
    WEREWOLF_LOG_FILE_BACKUP_COUNT=3 \
    WEREWOLF_LOG_THIRD_PARTY_LEVEL=WARNING

RUN uv sync --frozen --no-dev --extra api --extra llm --extra streamlit --extra worker
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app

USER app

CMD ["werewolf-agent-worker", "run"]
