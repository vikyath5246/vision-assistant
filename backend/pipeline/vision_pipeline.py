"""Vision Pipeline Orchestrator
Adapts offline-voice-ai VoicePipeline to handle vision (webcam frames) + Gemini
"""
import asyncio
import base64
import json
import logging
import os
import time
from typing import Optional, List, Dict, Set

import numpy as np
from fastapi import WebSocket

from config import (
    CHUNK_SIZE, SAMPLE_RATE, MIN_SEGMENT_DURATION,
    MAX_TRANSCRIPTION_QUEUE_SIZE, ENABLE_TRANSCRIPTION, ENABLE_TTS
)
from pipeline.audio_buffer import split_audio_into_chunks
from pipeline.speech_detector import SpeechDetector, PipelineEvent
from pipeline.scene_state import SceneState

logger = logging.getLogger(__name__)


def encode_audio(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_float32_audio(data: str) -> Optional[np.ndarray]:
    try:
        audio_bytes = base64.b64decode(data.encode("ascii"))
        return np.frombuffer(audio_bytes, dtype=np.float32) if len(audio_bytes) % 4 == 0 else None
    except Exception:
        return None


# Module-level set of dashboard subscribers (SSE queues)
_dashboard_subscribers: Set[asyncio.Queue] = set()


def register_dashboard_subscriber(q: asyncio.Queue):
    _dashboard_subscribers.add(q)


def unregister_dashboard_subscriber(q: asyncio.Queue):
    _dashboard_subscribers.discard(q)


async def broadcast_dashboard_event(event: dict):
    """Broadcast metrics/status to all connected dashboard SSE clients"""
    dead = set()
    for q in _dashboard_subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    _dashboard_subscribers.difference_update(dead)


class VisionPipeline:
    """Per-session orchestrator: audio → VAD → STT → vision → Gemini → TTS"""

    def __init__(self, ws: WebSocket, session_id: str, resources, initial_history: list = None):
        self.ws = ws
        self.session_id = session_id
        self.resources = resources

        self.detector = SpeechDetector()

        # Conversation history: [{role, content, frame?}]
        self.conversation: List[Dict] = []
        if initial_history:
            # Restore from DB (Turn objects → dict)
            for turn in initial_history:
                self.conversation.append({
                    "role": turn.role,
                    "content": turn.content,
                    "frame": None  # Frames not reloaded for API calls (cost control)
                })
            logger.info("[pipeline] Restored %d turns from history", len(initial_history))

        self.transcription_queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_TRANSCRIPTION_QUEUE_SIZE)
        self.accumulated_text = ""
        self.is_accumulating = False

        # Frame exchange: server requests frame, client sends back base64 JPEG
        self._frame_future: Optional[asyncio.Future] = None

        # Per-turn metrics (reset each turn)
        self._stt_latency_ms: Optional[int] = None
        self._llm_first_token_ms: Optional[int] = None
        self._tts_first_audio_ms: Optional[int] = None
        self._current_frame: Optional[str] = None  # base64 JPEG for this turn

        self._transcription_task: Optional[asyncio.Task] = None
        self._finalize_task: Optional[asyncio.Task] = None
        self._response_task: Optional[asyncio.Task] = None
        self._response_lock = asyncio.Lock()
        self._response_cancel_event: Optional[asyncio.Event] = None
        self._tts_mode = "server"  # "server" sends WAV media events, "client" delegates speech to browser

        # Background scene state (continuously updated by client-pushed scene_frame events)
        self.scene_state: Optional[SceneState] = None

    async def start(self):
        self._transcription_task = asyncio.create_task(self._transcription_worker())
        await self._send_state()
        logger.info("[pipeline:%s] Started", self.session_id)

    async def shutdown(self):
        if self._response_cancel_event and not self._response_cancel_event.is_set():
            self._response_cancel_event.set()

        await self._cancel_finalize_task()
        await self._cancel_response_task()

        if self._transcription_task:
            self._transcription_task.cancel()
            try:
                await self._transcription_task
            except asyncio.CancelledError:
                pass
            self._transcription_task = None

        logger.info("[pipeline:%s] Shutdown", self.session_id)

    async def handle_message(self, payload: dict):
        event = payload.get("event")

        if event == "start":
            self.detector.start_listening()
            await self._send_state()

        elif event == "stop":
            if payload.get("target") == "playback":
                await self._interrupt_response(notify_client=True)
            else:
                self.detector.stop_listening()
            await self._send_state()

        elif event == "media":
            await self._handle_audio(payload.get("audio"))

        elif event == "frame":
            # Client responded to our capture_frame request
            image = payload.get("image")
            logger.info("[pipeline] Frame response event received (%d bytes)", len(image) if image else 0)
            if self._frame_future and not self._frame_future.done():
                self._frame_future.set_result(image)

        elif event == "interrupt":
            await self._interrupt_response(notify_client=True)
            await self._send_state()

        elif event == "scene_frame":
            # Client-pushed background frame for continuous scene processing
            image = payload.get("image")
            if image and self.resources.scene_detector:
                asyncio.create_task(self._process_scene_frame(image))

        elif event == "config":
            tts_mode = payload.get("tts_mode")
            if tts_mode in {"server", "client"}:
                self._tts_mode = tts_mode
                logger.info("[pipeline] TTS mode set to: %s", self._tts_mode)

    async def _handle_audio(self, audio_data: str):
        if not audio_data:
            return

        audio = decode_float32_audio(audio_data)
        if audio is None or len(audio) == 0:
            return

        for chunk in split_audio_into_chunks(audio, CHUNK_SIZE):
            events = self.detector.process_chunk(chunk)
            if events:
                await self._handle_events(events)

        await self._send_state()

    async def _handle_events(self, events: List[PipelineEvent]):
        if PipelineEvent.SPEECH_START in events:
            self.is_accumulating = True
            self.accumulated_text = ""
            self._stt_latency_ms = None
            self._llm_first_token_ms = None
            self._tts_first_audio_ms = None
            self._current_frame = None

            if (
                self.detector.is_responding
                or (self._response_task and not self._response_task.done())
                or (self._finalize_task and not self._finalize_task.done())
            ):
                await self._interrupt_response(notify_client=True)

        for event in events:
            if event == PipelineEvent.TRANSCRIBE:
                await self._queue_transcription()
            elif event == PipelineEvent.RESPOND:
                self._schedule_finalize_and_respond()
            elif event in [PipelineEvent.SPEECH_START, PipelineEvent.SPEECH_END]:
                await self.ws.send_text(json.dumps({"event": event.value}))

        await self._send_state()

    async def _queue_transcription(self):
        if not self.resources.transcriber or self.detector.current_segment is None:
            return

        segment = self.detector.current_segment
        if len(segment) < SAMPLE_RATE * MIN_SEGMENT_DURATION:
            return

        self.detector.segment_count += 1
        segment_id = self.detector.segment_count

        try:
            self.transcription_queue.put_nowait((segment_id, segment))
            logger.info("[transcribe] Queued segment #%d", segment_id)
        except asyncio.QueueFull:
            logger.warning("[transcribe] Queue full, dropped segment #%d", segment_id)

    async def _transcription_worker(self):
        """Background worker: dequeues audio segments and transcribes them"""
        if not self.resources.transcriber:
            return

        logger.info("[transcribe] Worker started")

        while True:
            segment_id, audio = await self.transcription_queue.get()

            try:
                await self._send_metrics(stt={"status": "running", "segment_id": segment_id})

                stt_start = time.monotonic()
                # faster-whisper is thread-safe; no global lock needed
                transcript = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.resources.transcriber.transcribe,
                    audio
                )
                stt_elapsed_ms = int((time.monotonic() - stt_start) * 1000)
                self._stt_latency_ms = stt_elapsed_ms

                await self._send_metrics(stt={
                    "status": "completed",
                    "segment_id": segment_id,
                    "latency_ms": stt_elapsed_ms
                })

                if transcript and transcript.strip():
                    logger.info("[transcribe] #%d: %r (%.0fms)", segment_id, transcript, stt_elapsed_ms)

                    if self.is_accumulating:
                        if self.accumulated_text:
                            self.accumulated_text += " " + transcript.strip()
                        else:
                            self.accumulated_text = transcript.strip()

                        await self.ws.send_text(json.dumps({
                            "event": "text",
                            "role": "user",
                            "text": transcript.strip(),
                            "segment_id": segment_id,
                            "partial": True
                        }))

            except Exception as e:
                logger.error("[transcribe] Error on segment #%d: %s", segment_id, e, exc_info=True)

            finally:
                self.transcription_queue.task_done()

    async def _finalize_and_respond(self):
        """Wait for pending transcriptions then capture frame and generate response"""
        if self.transcription_queue.qsize() > 0:
            logger.info("[pipeline] Waiting for %d pending transcriptions", self.transcription_queue.qsize())
            await self.transcription_queue.join()

        self.is_accumulating = False

        if not self.accumulated_text:
            logger.info("[pipeline] No text accumulated, skipping response")
            return

        final_text = self.accumulated_text.strip()
        logger.info("[pipeline] Final transcript: %r", final_text)

        # Request current video frame from client
        frame_base64 = await self._request_frame()
        self._current_frame = frame_base64

        # Build LLM content: inject scene context as a parenthetical prefix so the
        # model knows what objects are visible even before seeing the frame.
        # The DB and the client always receive the clean user text (no prefix).
        scene_ctx = self.scene_state.to_context_string() if self.scene_state else ""
        llm_content = f"[{scene_ctx}]\n{final_text}" if scene_ctx else final_text

        # Add user turn to in-memory conversation (LLM sees augmented content)
        self.conversation.append({
            "role": "user",
            "content": llm_content,
            "frame": frame_base64
        })

        # Persist user turn to DB (clean text, not the injected context)
        await self._persist_turn("user", final_text)

        # Send complete transcript to client (clean text)
        await self.ws.send_text(json.dumps({
            "event": "text",
            "role": "user",
            "text": final_text,
            "complete": True
        }))

        self.accumulated_text = ""
        await self._start_response()

    def _schedule_finalize_and_respond(self):
        task = self._finalize_task
        if task and not task.done():
            return

        task = asyncio.create_task(self._finalize_and_respond())
        self._finalize_task = task
        task.add_done_callback(self._on_finalize_done)

    def _on_finalize_done(self, task: asyncio.Task):
        if self._finalize_task is task:
            self._finalize_task = None

        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("[pipeline] Finalize task cancelled")
        except Exception as e:
            logger.error("[pipeline] Finalize task error: %s", e, exc_info=True)

    async def _request_frame(self) -> Optional[str]:
        """Ask client to send current webcam frame, wait up to 3s"""
        loop = asyncio.get_event_loop()
        self._frame_future = loop.create_future()

        try:
            await self.ws.send_text(json.dumps({"event": "capture_frame"}))
            frame = await asyncio.wait_for(self._frame_future, timeout=3.0)
            logger.info("[pipeline] Frame received (%d bytes)", len(frame) if frame else 0)
            return frame
        except asyncio.CancelledError:
            logger.info("[pipeline] Frame request cancelled")
            raise
        except asyncio.TimeoutError:
            logger.warning("[pipeline] Frame request timed out, proceeding without frame")
            return None
        except Exception as e:
            logger.error("[pipeline] Frame request error: %s", e)
            return None
        finally:
            self._frame_future = None

    async def _start_response(self):
        async with self._response_lock:
            await self._cancel_response_task()
            self._response_cancel_event = asyncio.Event()
            self._response_task = asyncio.create_task(
                self._generate_response(self._response_cancel_event)
            )

    async def _cancel_response_task(self) -> bool:
        task = self._response_task
        if not task:
            return False

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._response_task = None
        return True

    async def _generate_response(self, cancel_event: asyncio.Event):
        """Stream response chunks and emit TTS in sentence-sized segments."""
        try:
            if not self.conversation or cancel_event.is_set():
                return

            self.detector.is_responding = True
            await self._send_state()

            last_user = next((m for m in reversed(self.conversation) if m["role"] == "user"), None)
            if not last_user:
                return

            logger.info("[response] Generating for: %r", last_user["content"])

            full_response_chunks = []
            llm_start = time.monotonic()
            first_llm_time = None
            first_tts_time = None
            tts_start = None
            idx = 0
            tts_buffer = ""
            tts_delimiters = {".", "!", "?", "\n"}

            async for chunk in self.resources.gemini_client.generate_streaming(self.conversation):
                if cancel_event.is_set() or not self.detector.is_responding:
                    logger.info("[response] Interrupted mid-stream")
                    break

                full_response_chunks.append(chunk)

                if first_llm_time is None:
                    first_llm_time = time.monotonic() - llm_start
                    self._llm_first_token_ms = int(first_llm_time * 1000)
                    await self._send_metrics(llm={"first_token_ms": self._llm_first_token_ms})

                # Stream raw chunks for ChatGPT-like progressive rendering
                await self.ws.send_text(json.dumps({
                    "event": "text",
                    "role": "assistant",
                    "text": chunk,
                    "streaming": True
                }))

                if ENABLE_TTS and self.resources.tts_handler and self._tts_mode != "client":
                    tts_buffer += chunk
                    while True:
                        split_idx = -1
                        for i, ch in enumerate(tts_buffer):
                            if ch in tts_delimiters:
                                split_idx = i
                                break

                        if split_idx == -1:
                            break

                        tts_text = tts_buffer[:split_idx + 1].strip()
                        tts_buffer = tts_buffer[split_idx + 1:]

                        if not tts_text:
                            continue

                        if tts_start is None:
                            tts_start = time.monotonic()

                        sent_audio = await self._send_tts(tts_text, idx, cancel_event)
                        if sent_audio and first_tts_time is None:
                            first_tts_time = time.monotonic() - tts_start
                            self._tts_first_audio_ms = int(first_tts_time * 1000)
                            await self._send_metrics(tts={"first_audio_ms": self._tts_first_audio_ms})
                        idx += 1

            if (
                ENABLE_TTS
                and self.resources.tts_handler
                and self._tts_mode != "client"
                and tts_buffer.strip()
                and not cancel_event.is_set()
            ):
                if tts_start is None:
                    tts_start = time.monotonic()
                sent_audio = await self._send_tts(tts_buffer.strip(), idx, cancel_event)
                if sent_audio and first_tts_time is None:
                    first_tts_time = time.monotonic() - tts_start
                    self._tts_first_audio_ms = int(first_tts_time * 1000)
                    await self._send_metrics(tts={"first_audio_ms": self._tts_first_audio_ms})

            complete = "".join(full_response_chunks).strip()
            if complete and self.detector.is_responding and not cancel_event.is_set():
                # Add assistant turn to conversation
                self.conversation.append({"role": "assistant", "content": complete, "frame": None})

                # Persist to DB
                await self._persist_turn("assistant", complete)

                # Send complete message (for display finalization)
                await self.ws.send_text(json.dumps({
                    "event": "text",
                    "role": "assistant",
                    "text": complete,
                    "complete": True
                }))

                logger.info("[response] Complete (first_llm=%.2fs)", first_llm_time or 0)

                # Broadcast metrics to dashboard
                await broadcast_dashboard_event({
                    "type": "turn_complete",
                    "session_id": self.session_id,
                    "stt_latency_ms": self._stt_latency_ms,
                    "llm_first_token_ms": self._llm_first_token_ms,
                    "tts_first_audio_ms": self._tts_first_audio_ms,
                    "response_length": len(complete)
                })

        except asyncio.CancelledError:
            logger.info("[response] Cancelled")
            raise

        except Exception as e:
            logger.error("[response] Error: %s", e, exc_info=True)
            step = "vision_api" if "gemini" in str(type(self.resources.gemini_client)).lower() else "response"
            try:
                await self.ws.send_text(json.dumps({
                    "event": "error",
                    "message": f"Failed to generate response: {str(e)[:100]}",
                    "step": step
                }))
            except Exception:
                pass

        finally:
            self.detector.is_responding = False
            await self._send_state()
            if self._response_cancel_event is cancel_event:
                self._response_cancel_event = None

    async def _process_scene_frame(self, frame_b64: str):
        """Run YOLOv8n on a client-pushed background frame.

        Updates self.scene_state and sends annotation boxes to the frontend.
        Runs as a fire-and-forget task so it never blocks the audio pipeline.
        """
        try:
            scene = await self.resources.scene_detector.process_frame_b64(frame_b64)
            if scene is None:
                return
            self.scene_state = scene
            # Send bounding boxes to frontend for the annotation overlay
            await self.ws.send_text(json.dumps({
                "event": "annotations",
                "boxes": scene.to_annotation_payload(),
                "timestamp": scene.timestamp,
            }))
        except Exception as e:
            logger.debug("[scene] _process_scene_frame error: %s", e)

    async def _send_tts(self, text: str, index: int, cancel_event: asyncio.Event) -> bool:
        """Generate TTS audio and send to client"""
        try:
            if cancel_event.is_set():
                return False

            audio_bytes = await self.resources.tts_handler.generate_speech_async(text)

            if cancel_event.is_set() or not self.detector.is_responding:
                return False

            if audio_bytes:
                await self.ws.send_text(json.dumps({
                    "event": "media",
                    "mime": "audio/wav",
                    "audio": encode_audio(audio_bytes),
                    "index": index
                }))
                logger.debug("[tts] Sent %d bytes (index=%d)", len(audio_bytes), index)
                return True

            return False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("[tts] Error: %s", e)
            return False

    async def _persist_turn(self, role: str, content: str):
        """Save turn to DB."""
        try:
            db = self.resources.db_session()
            try:
                from db import crud
                crud.save_turn(
                    db=db,
                    session_id=self.session_id,
                    role=role,
                    content=content,
                    stt_latency_ms=self._stt_latency_ms if role == "user" else None,
                    llm_first_token_ms=self._llm_first_token_ms if role == "assistant" else None,
                    tts_first_audio_ms=self._tts_first_audio_ms if role == "assistant" else None,
                )
            finally:
                db.close()
        except Exception as e:
            logger.error("[pipeline] Failed to persist turn: %s", e)

    async def _interrupt_response(self, notify_client: bool = False) -> bool:
        interrupted = False

        finalize_cancelled = await self._cancel_finalize_task()
        if finalize_cancelled:
            interrupted = True

        cancel_event = self._response_cancel_event
        if cancel_event and not cancel_event.is_set():
            cancel_event.set()
            interrupted = True

        async with self._response_lock:
            task_cancelled = await self._cancel_response_task()
            if self._response_cancel_event and self._response_cancel_event.is_set() and not self._response_task:
                self._response_cancel_event = None

        if task_cancelled:
            interrupted = True

        if self.detector.is_responding:
            self.detector.is_responding = False
            interrupted = True

        if interrupted:
            if self.conversation and self.conversation[-1]["role"] == "assistant":
                self.conversation.pop()
                logger.info("[interrupt] Removed incomplete assistant turn")

            if notify_client:
                await self.ws.send_text(json.dumps({"event": "interrupt"}))

        return interrupted

    async def _cancel_finalize_task(self) -> bool:
        task = self._finalize_task
        if not task:
            return False

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._finalize_task = None
        return True

    async def _send_metrics(self, stt: Optional[dict] = None, llm: Optional[dict] = None, tts: Optional[dict] = None):
        payload = {}
        if stt is not None:
            payload["stt"] = stt
        if llm is not None:
            payload["llm"] = llm
        if tts is not None:
            payload["tts"] = tts

        if payload:
            await self.ws.send_text(json.dumps({"event": "metrics", "metrics": payload}))

    async def _send_state(self):
        await self.ws.send_text(json.dumps({
            "event": "state",
            **self.detector.get_state()
        }))
