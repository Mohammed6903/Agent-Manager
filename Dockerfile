FROM python:3.11-slim

# Install Node.js (required by the openclaw CLI)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install openclaw CLI globally
RUN npm install -g openclaw@2026.2.17

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent_manager/ agent_manager/

# Default state directory
ENV OPENCLAW_STATE_DIR=/root/.openclaw
ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8000

EXPOSE 8000

CMD ["python", "-m", "agent_manager.main"]
