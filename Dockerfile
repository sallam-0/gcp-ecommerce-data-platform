FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/api/requirements.txt

COPY api /app/api
COPY scrappers /app/scrappers

RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
