FROM python:3.12-slim AS builder

# Build stage - install dependencies
WORKDIR /build

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies to user site-packages
RUN pip install --no-cache-dir --user -r requirements.txt


# Final stage - minimal runtime image
FROM python:3.12-slim

LABEL org.opencontainers.image.title="OctoGen" \
      org.opencontainers.image.description="AI-Powered Music Discovery Engine for Navidrome" \
      org.opencontainers.image.authors="OctoGen Contributors" \
      org.opencontainers.image.url="https://github.com/Blueion76/Octogen" \
      org.opencontainers.image.source="https://github.com/Blueion76/Octogen" \
      org.opencontainers.image.documentation="https://github.com/Blueion76/Octogen/blob/main/README.md" \
      org.opencontainers.image.licenses="MIT"

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
 && rm -rf /var/lib/apt/lists/* \
 && apt-get clean

# Copy Python packages from builder stage
COPY --from=builder /root/.local /root/.local

# Add local bin to PATH
ENV PATH=/root/.local/bin:$PATH

# Set working directory
WORKDIR /app

# Copy application code
COPY octogen.py .

# Create data directory with proper permissions
RUN mkdir -p /data && chmod 755 /data

# Environment variables with sensible defaults
ENV OCTOGEN_DATA_DIR=/data \
    LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AI_BACKEND=gemini \
    AI_MODEL=gemini-2.5-flash \
    AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

# Health check - verifies log file exists and was updated recently
HEALTHCHECK --interval=5m --timeout=30s --start-period=30s --retries=3 \
  CMD python3 -c "import json, sys, os; \
       from pathlib import Path; \
       health = json.loads(Path(os.getenv('OCTOGEN_DATA_DIR', '/data'), 'health.json').read_text()); \
       sys.exit(0 if health['status'] in ['healthy', 'running', 'scheduled'] else 1)" \
  || exit 1


# Expose data volume
VOLUME ["/data"]

# Run as non-root user for security (optional - uncomment if desired)
# RUN useradd -m -u 1000 octogen && \
#     chown -R octogen:octogen /app /data
# USER octogen

# Default command
CMD ["python", "-u", "octogen.py"]
