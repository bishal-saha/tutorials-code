# Build from the series folder so the shared pyproject.toml and uv.lock are in context:
#   docker build -f 03-production/05-ship-it/Dockerfile -t helpline-mcp .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY 03-production/05-ship-it/ ./server/
WORKDIR /app/server

# Run as an unprivileged user.
RUN useradd --system --uid 10001 helpline
USER helpline

ENV PORT=8000
EXPOSE 8000
# Production: set HELPLINE_ISSUER, HELPLINE_JWKS_URI and HELPLINE_RESOURCE_URL.
# Local try-out with the test issuer: set HELPLINE_DEV=1 and supply a key via HELPLINE_DEV_KEY.
CMD ["/opt/venv/bin/python", "main.py", "--host", "0.0.0.0"]
