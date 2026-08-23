FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data

# Expose default port
EXPOSE 10000

# Start the server with dynamic port fallback for Render ($PORT)
CMD sh -c "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"
