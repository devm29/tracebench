# Build context is the repository root so the image can also run the demo apps and seeder.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
COPY examples examples
RUN pip install "./backend[embeddings]" ./examples

FROM base AS runtime
RUN useradd --create-home --uid 10001 tracebench
COPY --from=build /opt/venv /opt/venv
COPY backend/alembic.ini backend/alembic.ini
COPY backend/migrations backend/migrations
ENV PATH="/opt/venv/bin:$PATH" \
    TRACEBENCH_LOG_JSON=true \
    TRACEBENCH_EMBEDDINGS_CACHE_DIR=/home/tracebench/.cache/fastembed
USER tracebench
WORKDIR /app/backend
EXPOSE 8105
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8105/api/health')" || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn --factory tracebench.main:create_app --host 0.0.0.0 --port 8105 --proxy-headers"]
