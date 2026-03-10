FROM python:3.11-slim AS builder

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# -------------------------------------------------------------------
FROM python:3.11-slim

RUN groupadd --gid 1000 oopsie \
    && useradd --uid 1000 --gid oopsie --create-home oopsie

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY alembic.ini ./
COPY alembic alembic/
COPY oopsie oopsie/
COPY templates templates/
COPY static static/
COPY docker-entrypoint.sh ./

RUN chown -R oopsie:oopsie /app
USER oopsie

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD uvicorn oopsie.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log
