# Agent service image: FastAPI + Microsoft Agent Framework 1.0 agents.
# Multi-stage: build deps with uv, ship a slim non-root runtime.
# Build:  docker build -t food-ingredients-agentic-ai:local .
# Run:    docker run -p 8000:8000 food-ingredients-agentic-ai:local

# syntax=docker/dockerfile:1

# Base image pinned by digest (python:3.12-slim, amd64, resolved 2026-10-11).
# Re-pin on rebuilds: docker buildx imagetools inspect python:3.12-slim.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app

# Install the project (non-editable) into the system site-packages.
COPY pyproject.toml README.md LICENSE ./
COPY food_ingredients_ai ./food_ingredients_ai
RUN uv pip install --system --no-cache .

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Non-root service user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local /usr/local

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "food_ingredients_ai.service.app:app", "--host", "0.0.0.0", "--port", "8000"]
