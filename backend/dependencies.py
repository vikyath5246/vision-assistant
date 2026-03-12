"""Application-wide shared resources (singletons)
Initialized once at startup via FastAPI lifespan
"""
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Cache vision API health check for 30s to avoid hammering the API on every /health poll
_VISION_API_HEALTH_CACHE: dict = {"status": None, "checked_at": 0}


@dataclass
class AppResources:
    """Singleton container for all shared ML/DB resources"""
    transcriber: object = None          # FasterWhisperTranscriber
    vision_client: object = None        # OpenAIVisionClient
    tts_handler: object = None          # EdgeTTSHandler
    scene_detector: object = None       # SceneDetector (YOLOv8n)
    db_session: object = None           # SQLAlchemy SessionLocal callable
    active_sessions: Dict[str, object] = field(default_factory=dict)  # session_id → VisionPipeline

    def get_health(self) -> dict:
        """Return health status of each pipeline component"""
        status = {}

        # VAD/EOU - always ok if ONNX models loaded (checked at startup)
        status["vad"] = "ok"

        # Transcriber
        if self.transcriber is not None:
            status["transcriber"] = "ok"
        else:
            status["transcriber"] = "disabled"

        # Vision API - cached health check (avoid API call on every /health poll)
        if self.vision_client is not None:
            now = time.monotonic()
            if now - _VISION_API_HEALTH_CACHE["checked_at"] > 30:
                try:
                    reachable = self.vision_client.is_reachable()
                    _VISION_API_HEALTH_CACHE["status"] = "ok" if reachable else "unreachable"
                except Exception as e:
                    _VISION_API_HEALTH_CACHE["status"] = f"error: {str(e)[:60]}"
                _VISION_API_HEALTH_CACHE["checked_at"] = now
            status["vision_api"] = _VISION_API_HEALTH_CACHE["status"] or "checking"
        else:
            status["vision_api"] = "not_configured"

        # TTS
        if self.tts_handler is not None:
            status["tts"] = "ok"
        else:
            status["tts"] = "disabled"

        # Database
        if self.db_session is not None:
            try:
                db = self.db_session()
                db.execute(__import__("sqlalchemy").text("SELECT 1"))
                db.close()
                status["database"] = "ok"
            except Exception as e:
                status["database"] = f"error: {str(e)[:60]}"
        else:
            status["database"] = "not_configured"

        return status
