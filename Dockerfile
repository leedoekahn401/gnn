FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file and install
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy the application source code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data
