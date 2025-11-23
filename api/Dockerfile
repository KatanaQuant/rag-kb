# syntax=docker/dockerfile:1

# ============================================================================
# Stage 1: Builder - Install and compile Python packages
# ============================================================================
FROM python:3.11-slim AS builder

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
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install only runtime system dependencies (no build tools)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
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
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY . .

# Create data directory and model cache
RUN mkdir -p /app/data /app/.cache/deepsearch_glm

# Create model directories and make them writable (in venv)
RUN mkdir -p /opt/venv/lib/python3.11/site-packages/deepsearch_glm/resources/models/crf/part-of-speech && \
    mkdir -p /opt/venv/lib/python3.11/site-packages/rapidocr/models

# Run as non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /opt/venv

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
