# Build stage
FROM python:3.12.3-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (excluding sentence-transformers)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Final stage
FROM python:3.12.3-slim

WORKDIR /app

# Copy only the necessary files from the builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY . .

EXPOSE 8000

# Create a startup script
RUN echo '#!/bin/bash\npip install sentence-transformers\npip install peft\nuvicorn api:app --host 0.0.0.0 --port 8000' > /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]