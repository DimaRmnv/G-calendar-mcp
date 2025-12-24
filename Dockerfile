# Google Calendar MCP Server - Cloud Deployment
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Install package with cloud dependencies
RUN pip install --no-cache-dir -e ".[cloud]"

# Create data directory
RUN mkdir -p /data/credentials

# Environment variables
ENV GCAL_MCP_TRANSPORT_MODE=http
ENV GCAL_MCP_HTTP_HOST=0.0.0.0
ENV GCAL_MCP_HTTP_PORT=8000
ENV GCAL_MCP_DATA_DIR=/data
ENV GCAL_MCP_CREDENTIALS_DIR=/data/credentials

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["python", "-m", "google_calendar", "serve"]
