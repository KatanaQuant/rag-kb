# syntax=docker/dockerfile:1

# ============================================================================
# Stage 1: Builder - Install and compile Python packages
# ============================================================================
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build dependencies for compiling Python packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for Python packages
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python packages
COPY requirements.txt .

# Install Python packages with BuildKit cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal runtime environment
# ============================================================================
FROM python:3.13-slim AS runtime

WORKDIR /app

# Create non-root user EARLY (before any COPY commands)
# This allows --chown flag to work without creating duplicate layers
RUN useradd -m -u 1000 appuser

# Install only runtime system dependencies (no build tools)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sudo \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    pandoc \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-latex-extra \
    texlive-plain-generic \
    texlive-xetex \
    lmodern \
    ghostscript \
    chromium \
    clamav \
    clamav-daemon \
    clamav-freshclam \
    libyara10 \
    yara \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder stage WITH correct ownership (no extra chown layer)
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code WITH correct ownership
COPY --chown=appuser:appuser . .

# Create data directory and model cache (owned by appuser via --chown above)
RUN mkdir -p /app/data /app/.cache/deepsearch_glm

# Create model directories and make them writable (already owned by appuser via --chown)
RUN mkdir -p /opt/venv/lib/python3.13/site-packages/deepsearch_glm/resources/models/crf/part-of-speech && \
    mkdir -p /opt/venv/lib/python3.13/site-packages/rapidocr/models

# Setup ClamAV directories and permissions
RUN mkdir -p /var/lib/clamav /var/log/clamav /run/clamav && \
    chown -R clamav:clamav /var/lib/clamav /var/log/clamav /run/clamav

# Skip signature download during build - let runtime handle it via bind mount
# Signatures will be downloaded once on first container start to .cache/clamav
# then reused across container restarts and rebuilds
# This saves ~350MB image size and ~6 min build time (after initial download)

# Copy and set up entrypoint script
COPY --chown=appuser:appuser docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Configure sudo for ClamAV (appuser already created above)
RUN echo "appuser ALL=(clamav) NOPASSWD: /usr/sbin/clamd, /usr/bin/freshclam" >> /etc/sudoers

USER appuser

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
