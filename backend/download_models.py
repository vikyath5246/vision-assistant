"""Pre-download script for all models.
Run before starting the server:
  python download_models.py

Downloads:
  - faster-whisper STT model (~74 MB for base)
  - YOLOv8n object-detection weights (~6 MB)
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def download_whisper():
    from dotenv import load_dotenv
    load_dotenv()
    model_size = os.getenv("WHISPER_MODEL_SIZE", "base")

    logger.info("Downloading faster-whisper model: %s", model_size)
    logger.info("This downloads ~%s to models/whisper_cache/", {
        "tiny": "39MB", "base": "74MB", "small": "244MB",
        "medium": "769MB", "large-v3": "1.5GB"
    }.get(model_size, "?"))

    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8",
                         download_root="models/whisper_cache")
    logger.info("Whisper model downloaded and ready!")

    import numpy as np
    dummy = np.zeros(16000, dtype=np.float32)
    segments, _ = model.transcribe(dummy, beam_size=1, language="en")
    list(segments)
    logger.info("Whisper validation successful")


def download_yolo():
    from dotenv import load_dotenv
    load_dotenv()

    enable = os.getenv("ENABLE_BACKGROUND_SCENE", "true").lower() == "true"
    if not enable:
        logger.info("ENABLE_BACKGROUND_SCENE=false — skipping YOLOv8n download")
        return

    model_path = os.getenv("YOLO_MODEL_PATH", "models/yolov8n.pt")
    os.makedirs(os.path.dirname(model_path) or "models", exist_ok=True)

    if os.path.exists(model_path):
        logger.info("YOLOv8n already present at %s", model_path)
    else:
        logger.info("Downloading YOLOv8n weights (~6 MB) ...")
        import shutil
        from ultralytics import YOLO
        # ultralytics downloads yolov8n.pt to ~/.cache/ultralytics/assets/
        m = YOLO("yolov8n.pt")
        src = getattr(m, "ckpt_path", None) or getattr(m.model, "pt_path", None)
        if src and os.path.exists(src):
            shutil.copy(src, model_path)
            logger.info("Copied YOLOv8n to %s", model_path)
        else:
            # ultralytics may have placed it in cwd
            if os.path.exists("yolov8n.pt"):
                shutil.move("yolov8n.pt", model_path)
            else:
                logger.warning("Could not locate downloaded yolov8n.pt; YOLO will re-download at startup")

    # Warm-up validation
    logger.info("Validating YOLOv8n inference ...")
    import numpy as np
    from ultralytics import YOLO
    m = YOLO(model_path)
    results = m(np.zeros((480, 640, 3), dtype=np.uint8), verbose=False)
    logger.info("YOLOv8n validation OK (%d detections on blank frame)", len(results[0].boxes))


def download_onnx_models():
    """Download silero_vad.onnx and smart_turn_v3.onnx if not already present."""
    import urllib.request

    models_dir = "models"
    os.makedirs(models_dir, exist_ok=True)

    files = {
        "silero_vad.onnx": (
            "https://raw.githubusercontent.com/snakers4/silero-vad/master"
            "/src/silero_vad/data/silero_vad.onnx"
        ),
        "smart_turn_v3.onnx": (
            "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main"
            "/smart-turn-v3.0.onnx"
        ),
    }

    for filename, url in files.items():
        dest = os.path.join(models_dir, filename)
        if os.path.exists(dest):
            logger.info("%s already present, skipping download", filename)
            continue
        logger.info("Downloading %s ...", filename)
        urllib.request.urlretrieve(url, dest)
        logger.info("Saved %s (%.1f MB)", dest, os.path.getsize(dest) / 1e6)


def main():
    try:
        download_onnx_models()
    except Exception as e:
        logger.error("ONNX model download failed: %s", e)
        sys.exit(1)

    try:
        download_whisper()
    except Exception as e:
        logger.error("Whisper download failed: %s", e)
        sys.exit(1)

    try:
        download_yolo()
    except Exception as e:
        logger.error("YOLOv8n download failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
