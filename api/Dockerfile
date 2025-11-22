FROM python:3.11-slim

WORKDIR /app

# Install system dependencies in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages (CPU-only, no CUDA)
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory and model cache
RUN mkdir -p /app/data /app/.cache/deepsearch_glm

# Create model directories and make them writable
RUN mkdir -p /usr/local/lib/python3.11/site-packages/deepsearch_glm/resources/models/crf/part-of-speech && \
    mkdir -p /usr/local/lib/python3.11/site-packages/rapidocr/models

# Run as non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /usr/local/lib/python3.11/site-packages/deepsearch_glm && \
    chown -R appuser:appuser /usr/local/lib/python3.11/site-packages/rapidocr

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
