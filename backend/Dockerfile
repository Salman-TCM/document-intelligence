FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home app
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install --no-cache-dir -r $([ "$INSTALL_DEV" = "true" ] && echo requirements-dev.txt || echo requirements.txt)

COPY . .
RUN mkdir -p /data/uploads /home/app/.cache && chown -R app /data /home/app/.cache
USER app

ENV UPLOAD_DIR=/data/uploads \
    FASTEMBED_CACHE_PATH=/home/app/.cache/fastembed \
    PYTHONUNBUFFERED=1 \
    OMP_THREAD_LIMIT=1

# Bake the embedding model into the image so the first request doesn't download it.
RUN python -c "from app.processing.embeddings import embed; embed('warm up')"
# The model is in the image now. Without this, fastembed still checks Hugging Face on
# every start and hangs when the network is slow.
ENV HF_HUB_OFFLINE=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
