# syntax=docker/dockerfile:1
#
# README, "Run it in Docker", has the commands.

FROM node:22-slim AS web
WORKDIR /app
COPY design/tokens.json design/tokens.json
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci
COPY web/ web/
RUN cd web && npm run build

FROM python:3.14-slim
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock LICENSE ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.15,source=/uv,target=/bin/uv uv sync --frozen --no-dev --no-install-project
COPY src/ src/
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.15,source=/uv,target=/bin/uv uv sync --frozen --no-dev
COPY --from=web /app/web/dist web/dist

# The run database lives in /app/.jk, a volume, so it survives a new image.
# A custom `docker run --user` needs a volume prepared for that user id.
RUN useradd --create-home --uid 1000 jk \
    && mkdir -p /app/.jk \
    && chown jk:jk /app/.jk \
    && chmod 0700 /app/.jk
USER jk
VOLUME ["/app/.jk"]
EXPOSE 8765

# Inside the container JK listens on every interface so Docker can forward the
# port; the run command publishes it on the host's loopback only.
ENTRYPOINT ["/app/.venv/bin/jk", "serve", "--host", "0.0.0.0", "--no-open"]
