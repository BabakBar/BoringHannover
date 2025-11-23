# =============================================================================
# KinoWeek Backend Dockerfile
# Multi-stage build for Python 3.13 with uv package manager
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build environment
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# Install uv - pinned version for reproducibility
COPY --from=ghcr.io/astral-sh/uv:0.5.6 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first (for layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ ./src/

# Install the project itself
RUN uv sync --frozen --no-dev

# -----------------------------------------------------------------------------
# Stage 2: Runtime environment
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

# Security: Create non-root user
RUN groupadd --gid 1000 kinoweek && \
    useradd --uid 1000 --gid kinoweek --shell /bin/bash --create-home kinoweek

# Install runtime dependencies (ca-certificates for HTTPS)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY --from=builder /app/src /app/src

# Copy additional files needed at runtime
COPY src/kinoweek/sources.toml /app/src/kinoweek/sources.toml

# Create output directory with correct permissions
RUN mkdir -p /app/output && chown -R kinoweek:kinoweek /app

# Switch to non-root user
USER kinoweek

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Default log level
    LOG_LEVEL=INFO

# Health check - verify Python and package are accessible
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import kinoweek; print('OK')" || exit 1

# Default command - run the scraper
# For cron execution, this will be overridden
CMD ["python", "-m", "kinoweek.main"]

# Labels for container metadata
LABEL org.opencontainers.image.title="KinoWeek Backend" \
      org.opencontainers.image.description="Weekly event aggregator for Hannover" \
      org.opencontainers.image.source="https://github.com/BabakBar/KinoWeek" \
      org.opencontainers.image.licenses="MIT"
