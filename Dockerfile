FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIVEFIRE_DATABASE_PATH=/data/livefirettx.db \
    LIVEFIRE_GENERATED_ROOT=/data/generated/exercises \
    LIVEFIRE_BACKUP_ROOT=/data/backups

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md LICENSE NOTICE /app/
COPY app /app/app
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 livefire \
    && mkdir -p /data \
    && chown -R livefire:livefire /data
USER livefire

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
