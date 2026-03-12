"""Conversational Vision Assistant - FastAPI Backend
Entry point: python main.py
"""
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import ENABLE_TRANSCRIPTION, ENABLE_TTS, ENABLE_BACKGROUND_SCENE, OPENAI_API_KEY
from dependencies import AppResources
from db.database import create_tables, SessionLocal
from api.websocket import router as ws_router
from api.sessions import router as sessions_router
from api.dashboard import router as dashboard_router

# Structured logging: include timestamp, level, and step name
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all pipeline resources on startup"""
    logger.info("=== Starting Vision Assistant ===")

    resources = AppResources()
    resources.db_session = SessionLocal

    # Create DB tables
    create_tables()
    logger.info("[startup] Database tables ready")

    # Load faster-whisper transcriber
    if ENABLE_TRANSCRIPTION:
        try:
            start = time.monotonic()
            from pipeline.transcriber import FasterWhisperTranscriber
            resources.transcriber = FasterWhisperTranscriber()

            # Warm up: run on dummy audio so first real transcription is fast
            dummy_audio = np.random.randn(16000).astype(np.float32) * 0.001
            resources.transcriber.transcribe(dummy_audio)

            logger.info("[startup] Transcriber ready (%.1fs)", time.monotonic() - start)
        except Exception as e:
            logger.error("[startup] Transcriber failed to load: %s", e)

    # Initialize OpenAI vision client
    if OPENAI_API_KEY:
        try:
            from vision.openai_client import OpenAIVisionClient
            resources.vision_client = OpenAIVisionClient()
            logger.info("[startup] OpenAI vision client ready")
        except Exception as e:
            logger.error("[startup] OpenAI client failed: %s", e)
    else:
        logger.warning("[startup] OPENAI_API_KEY not set - vision API disabled")

    # Initialize TTS
    if ENABLE_TTS:
        try:
            from pipeline.tts_handler import EdgeTTSHandler
            resources.tts_handler = EdgeTTSHandler()
            logger.info("[startup] TTS handler ready")
        except Exception as e:
            logger.error("[startup] TTS failed to load: %s", e)

    # Initialize YOLOv8n background scene detector
    if ENABLE_BACKGROUND_SCENE:
        try:
            start = time.monotonic()
            from pipeline.scene_detector import SceneDetector
            resources.scene_detector = SceneDetector()
            logger.info("[startup] Scene detector ready (%.1fs)", time.monotonic() - start)
        except Exception as e:
            logger.error("[startup] Scene detector failed to load: %s", e)
    else:
        logger.info("[startup] Background scene processing disabled by config")

    app.state.resources = resources
    logger.info("=== Vision Assistant Ready ===\n")

    yield

    # Cleanup on shutdown
    logger.info("=== Shutting down ===")
    for session_id, pipeline in list(resources.active_sessions.items()):
        try:
            await pipeline.shutdown()
        except Exception:
            pass


app = FastAPI(
    title="Vision Assistant API",
    description="Conversational Vision Assistant backend",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(ws_router)
app.include_router(sessions_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health_check():
    """Health endpoint with per-component status for operators and dashboard"""
    resources = app.state.resources
    component_status = resources.get_health()

    overall = "ok" if all(
        v in ("ok", "disabled") for v in component_status.values()
    ) else "degraded"

    return {
        "status": overall,
        "components": component_status,
        "active_sessions": len(resources.active_sessions),
        "session_ids": list(resources.active_sessions.keys())
    }


@app.get("/")
async def root():
    return {"message": "Vision Assistant API", "docs": "/docs", "health": "/health"}


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Vision Assistant on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
