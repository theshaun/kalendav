# Dockerfile for KalenDAV Server.
#
# Two stages:
#   1. frontend-build — Node 20, builds Vite assets into /build/app/static/dist.
#   2. runtime        — Python 3.11, copies the built dist/ in. Node deps and
#                       source stay in stage 1; only the hashed bundles ship.

# ---------------------------------------------------------------------------
# Stage 1: Build frontend assets
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /build

# Install deps first so the layer is cached when only source changes.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# Vite config, PostCSS, Tailwind, source, and design tokens.
COPY tailwind.config.js postcss.config.js vite.config.js ./
COPY app/static ./app/static

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Built frontend assets from stage 1.
COPY --from=frontend-build /build/app/static/dist ./app/static/dist

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
