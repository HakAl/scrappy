# E2E test environment: Node.js + Python for tui-test + scrappy
FROM node:20-bookworm-slim

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for python
RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copy full project
COPY . .

# Install scrappy and dependencies
RUN pip install --break-system-packages -e .

# Install Node.js dependencies for E2E tests
WORKDIR /app/tests/e2e
RUN npm install

# Back to app root
WORKDIR /app

# Run E2E tests
CMD ["npm", "--prefix", "tests/e2e", "test"]
