# syntax=docker/dockerfile:1
# VEYRA in one image: the web app is built with Node, then served by the FastAPI process beside the API.
#   docker build -t veyra .                      # demo build: fixtures + the ONNX muzzle matcher
#   docker build -t veyra --build-arg PERCEPTION=true .   # adds torch, ultralytics, open_clip (large)
#   docker run -p 8000:8000 veyra               # open http://localhost:8000

FROM node:22-bookworm-slim AS web
WORKDIR /app/apps/web
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/.npmrc ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

FROM python:3.12-slim-bookworm AS app
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
# OpenCV (headless) still needs glib at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/services/api
ARG PERCEPTION=false
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN if [ "$PERCEPTION" = "true" ]; then uv sync --frozen --no-dev --extra perception; \
    else uv sync --frozen --no-dev; fi
COPY services/api/ ./
COPY demo/ /app/demo/
COPY --from=web /app/apps/web/dist /app/web

ENV PATH="/app/services/api/.venv/bin:$PATH" \
    VEYRA_WEB_DIST=/app/web \
    VEYRA_DATA_DIR=/data \
    VEYRA_DEMO_MODE=1
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"
# One worker: the API keeps its job pool and replay threads in process (see persistence/db.py).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
