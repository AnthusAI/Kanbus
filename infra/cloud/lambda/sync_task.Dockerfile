FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY sync_worker.py /app/sync_worker.py

CMD ["python", "sync_worker.py"]
