FROM python:3.11-slim

WORKDIR /app

# System dependencies (psycopg2-binary needs libpq at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 (required for the openclaw CLI that agent_manager shells out to)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# git is required by some of openclaw's npm dependencies;
# force HTTPS instead of SSH so it works without an SSH key.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global url."https://github.com/".insteadOf ssh://git@github.com/ \
    && git config --global --add url."https://github.com/".insteadOf git@github.com:

# Install openclaw CLI globally so `openclaw gateway call …` works from Python
RUN npm install -g openclaw@2026.2.17

# Python dependencies — cached layer (only rebuilt when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Entrypoint: run DB migrations then start uvicorn
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
