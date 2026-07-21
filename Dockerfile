# Dockerfile for KalenDAV Server.
#
# Two stages:
#   1. frontend-build — Node 20, builds Vite assets into /build/app/static/dist.
#   2. runtime        — Python 3.11, copies the built dist/ in. Node deps and
#                       source stay in stage 1; only the hashed bundles ship.
#
# Build arg:
#   APP_VERSION — injected by CI on release builds; defaults to "dev".

# ---------------------------------------------------------------------------
# Stage 1: Build frontend assets
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /build

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY tailwind.config.js postcss.config.js vite.config.js ./
COPY app/static ./app/static

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ARG APP_VERSION=dev

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY --from=frontend-build /build/app/static/dist ./app/static/dist

LABEL org.opencontainers.image.title="KalenDAV"
LABEL org.opencontainers.image.description="Lightweight async CalDAV server"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.source="https://github.com/theshaun/KalenDAV"
LABEL org.opencontainers.image.licenses="MIT"

ENV APP_VERSION=${APP_VERSION}

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
