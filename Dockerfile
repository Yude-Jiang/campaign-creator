FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY templates ./templates
COPY static ./static
RUN mkdir -p /app/data/campaigns

RUN pip install --no-cache-dir .

EXPOSE 8080

# Cloud Run injects $PORT; the default above keeps `docker run` working locally.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
