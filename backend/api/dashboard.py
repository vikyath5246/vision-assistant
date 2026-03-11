"""Server-Sent Events dashboard endpoint
Streams real-time pipeline metrics to the frontend observability panel
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from pipeline.vision_pipeline import register_dashboard_subscriber, unregister_dashboard_subscriber

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard/events")
async def dashboard_events(request: Request):
    """SSE stream: sends real-time metrics from all active sessions"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    register_dashboard_subscriber(queue)

    async def event_generator():
        # Send initial state
        resources = request.app.state.resources
        active = list(resources.active_sessions.keys())
        yield f"data: {json.dumps({'type': 'connected', 'active_sessions': active})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_dashboard_subscriber(queue)
            logger.info("Dashboard SSE client disconnected")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
