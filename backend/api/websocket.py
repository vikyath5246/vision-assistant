"""WebSocket endpoint: /ws/{session_id}
Handles the full duplex audio/video/text conversation stream per session
"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

from db import crud
from pipeline.vision_pipeline import VisionPipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info("[ws:%s] Client connected", session_id)

    resources = websocket.app.state.resources

    # Ensure session exists in DB
    db = resources.db_session()
    try:
        crud.get_or_create_session(db, session_id)
        initial_history = crud.get_session_turns(db, session_id)
    finally:
        db.close()

    pipeline = VisionPipeline(
        ws=websocket,
        session_id=session_id,
        resources=resources,
        initial_history=initial_history
    )

    resources.active_sessions[session_id] = pipeline
    await pipeline.start()

    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("[ws:%s] Invalid JSON received", session_id)
                continue
            await pipeline.handle_message(payload)

    except WebSocketDisconnect:
        logger.info("[ws:%s] Client disconnected", session_id)

    except Exception as e:
        logger.error("[ws:%s] Unexpected error: %s", session_id, e, exc_info=True)
        try:
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "Connection error",
                "step": "websocket"
            }))
        except Exception:
            pass

    finally:
        resources.active_sessions.pop(session_id, None)
        await pipeline.shutdown()
        logger.info("[ws:%s] Pipeline cleaned up", session_id)
