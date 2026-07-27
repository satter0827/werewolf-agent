# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /workspace

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --group dev --extra api --extra llm --extra streamlit --extra worker --no-install-project
RUN python -m playwright install --with-deps chromium

COPY src ./src
RUN uv sync --frozen --group dev --extra api --extra llm --extra streamlit --extra worker
COPY scripts ./scripts
COPY contracts ./contracts
COPY supabase ./supabase
COPY .streamlit ./.streamlit

CMD ["python", "-m", "pytest", "scripts/browser/scenarios/test_streamlit.py"]
