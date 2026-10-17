# ==========================================
# AI Resume Intelligence System 2.0
# Multi-stage Docker Configuration
#
# Security features:
# - Non-root user
# - Minimal base image (slim)
# - No build tools in final image
# - Health check included
# - Explicit volume for persistent data
# ==========================================

# ---------- STAGE 1: Builder ----------
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install dependencies
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Download SpaCy model into the venv
RUN python -m spacy download en_core_web_sm

# Pre-download the sentence-transformers model so the container does not
# need network access at runtime (avoids slow cold starts).
# Set HF_HOME so the cache lands somewhere we can copy wholesale.
ENV HF_HOME=/opt/model_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"


# ---------- STAGE 2: Runtime ----------
FROM python:3.12-slim AS runtime

# Labels
LABEL org.opencontainers.image.title="AI Resume Intelligence System"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.description="Cloud-Based Hiring Copilot"

# Install only runtime dependencies (libmagic for MIME detection, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pre-downloaded model cache
COPY --from=builder /opt/model_cache /opt/model_cache
ENV HF_HOME=/opt/model_cache
# Prevent runtime downloads and telemetry
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV SENTENCE_TRANSFORMERS_HOME=/opt/model_cache/sentence_transformers

# Set working directory
WORKDIR /app

# Copy application code (owned by appuser)
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser frontend/ ./frontend/

# Create data directory for SQLite (persistent volume mount point)
RUN mkdir -p /app/backend/data && chown -R appuser:appuser /app/backend/data

# Switch to non-root user
USER appuser

# Environment defaults (overridable at runtime)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    DATABASE_PATH=/app/backend/data/resume_db.sqlite

# Expose port
EXPOSE 8000

# Health check — uses the stdlib so no curl dependency is strictly required
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Start the application
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
