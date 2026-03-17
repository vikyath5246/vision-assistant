FROM python:3.11-slim

# System dependencies:
#   ffmpeg      — required by pydub / edge-tts audio processing
#   libsndfile1 — required by soundfile
#   curl        — used by the compose healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (separate layer — only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download all models: silero_vad + smart_turn (ONNX), faster-whisper, YOLOv8n
# Separate COPY so this layer is only re-run when download_models.py itself changes
COPY download_models.py .
RUN python download_models.py

# Copy the rest of the application source
COPY . .

# Ensure the entrypoint script is executable and has Unix line endings
# (fixes Windows CRLF -> Docker issues)
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
