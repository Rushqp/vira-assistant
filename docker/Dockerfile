FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2

WORKDIR /app

RUN useradd --create-home --uid 1000 vira

# Optional PyPI mirror for the build (e.g. when pypi.org is blocked): PIP_INDEX_URL in .env
ARG PIP_INDEX_URL=

# Dependencies first (cached layer): read them straight from pyproject.toml
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}" pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /app/data && chown -R vira:vira /app/data

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
