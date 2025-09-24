FROM python:3.12-slim-bookworm AS base

# Builder stage - install dependencies with uv
FROM base AS builder

# Install uv (static binary)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Install only dependencies first to enable layer caching
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-install-project --no-dev

# Copy app source code and install the project itself
COPY src Readme.md /app/
RUN uv sync --frozen --no-dev

# Final runtime image
FROM base

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 80

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
