FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file and install
COPY pyproject.toml .

# Install CPU-only PyTorch first (avoids pulling the ~2GB CUDA version)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch-geometric

# Install remaining dependencies
RUN pip install --no-cache-dir .

# Copy the application source code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data
