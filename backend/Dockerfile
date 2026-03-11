FROM python:3.11-slim

# System dependencies:
#   ffmpeg      — required by pydub / edge-tts audio processing
#   libsndfile1 — required by soundfile
#   curl        — used by the compose healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (separate layer — only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the static ONNX models that live in the repo (VAD + EOU, ~3 MB each)
COPY models/silero_vad.onnx models/smart_turn_v3.onnx /app/models/

# Download dynamic models: faster-whisper (~74 MB) + YOLOv8n (~6 MB)
# Separate COPY so this layer is only re-run when download_models.py itself changes
COPY download_models.py .
RUN python download_models.py

# Copy the rest of the application source
COPY . .

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
