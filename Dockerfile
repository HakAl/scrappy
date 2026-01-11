FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy everything (uv sync needs src/ for editable install)
COPY . .

# Install package with all extras (includes dev dependencies)
RUN uv sync --frozen --all-extras

# Create non-root user for running tests
RUN useradd -m -u 1000 scrappy && \
    chown -R scrappy:scrappy /app

USER scrappy

# Default command runs tests
CMD ["uv", "run", "python", "-m", "pytest", "tests/", "-v", "--ignore=tests/e2e"]
