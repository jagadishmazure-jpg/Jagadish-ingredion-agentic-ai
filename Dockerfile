# Agent service image: FastAPI + Microsoft Agent Framework 1.0 agents.
# Multi-stage: build deps with uv, ship a slim non-root runtime.
# Build:  docker build -t ingredion-agentic-ai:local .
# Run:    docker run -p 8000:8000 ingredion-agentic-ai:local

# syntax=docker/dockerfile:1

# Base image pinned by digest (python:3.12-slim, amd64, resolved 2026-10-11).
# Re-pin on rebuilds: docker buildx imagetools inspect python:3.12-slim.
FROM python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app

# Install the project (non-editable) into the system site-packages.
COPY pyproject.toml README.md LICENSE ./
COPY ingredion_ai ./ingredion_ai
RUN uv pip install --system --no-cache .

FROM python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe AS runtime

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

CMD ["uvicorn", "ingredion_ai.service.app:app", "--host", "0.0.0.0", "--port", "8000"]
