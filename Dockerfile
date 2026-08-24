FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && addgroup --system app \
    && adduser --system --ingroup app app

# Only runtime inputs are copied. Repository history, tests, local databases,
# credentials, installers, and internal notes are excluded by design.
COPY server ./server
COPY frontend ./frontend

# Create a writable local-data location without running the service as root.
RUN mkdir -p /app/data && chown -R app:app /app
USER app

# Expose default port
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '10000') + '/health', timeout=3)"

CMD ["python", "-m", "server.runtime"]
