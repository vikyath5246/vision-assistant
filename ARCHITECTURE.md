# Architecture Decision Document
## Conversational Vision Assistant

---

## 1. Streaming Architecture

### What protocol(s) did I choose?

**Single WebSocket connection** per session handles all data flows: audio chunks (client→server), video frames (bidirectional request-response), text responses (server→client), and TTS audio (server→client).

### Video: Pull-based frame capture (not continuous streaming)

Rather than streaming video frames continuously (which would be expensive in bandwidth and tokens), the server uses a **pull model**:

1. VAD detects speech end → transcription completes
2. Server sends `{ event: "capture_frame" }` to the client
3. Client grabs the current canvas frame as JPEG (640×480, quality 0.7, ~30–80KB) and sends it back
4. Server waits up to 3 seconds, then proceeds with or without the frame

**Why this timing?** Capturing after transcription (not at speech-end) is more accurate. The user continues pointing at the object during the 300–1500ms transcription window. This yields a more relevant frame with no continuous video bandwidth cost.

### Background scene frames (continuous)

In addition to on-demand frame capture, the `useVideoCapture` hook pushes a JPEG frame to the backend every 1.5 seconds as `{ event: "scene_frame" }`. The server runs YOLOv8n inference on these frames in a fire-and-forget task to maintain a live scene state and send annotation overlays back to the frontend.

### Audio: Real-time 32ms chunks

Microphone audio is captured at 16kHz via `ScriptProcessorNode`, split into 512-sample (32ms) Float32 chunks, base64-encoded, and sent as `{ event: "media", audio: "..." }` JSON over the same WebSocket.

**Trade-offs considered:**
- **WebRTC**: Higher quality, built-in echo cancellation, better NAT traversal — but much more implementation complexity (signaling server, ICE, STUN/TURN). Overkill for a single-display demo where both ends are on localhost.
- **HTTP chunked streaming (fetch with ReadableStream)**: No bidirectional capability without a second connection.
- **WebSocket**: Simple, bidirectional, low overhead, well-supported. Sufficient for the latency targets required.

---

## 2. Vision API & Processing Pipeline

### What model? OpenAI gpt-4o-mini

**Why gpt-4o-mini:**
- **Vision support**: Accepts text + images via the Chat Completions API with the `image_url` content type
- **Cost**: $0.15/1M input tokens, $0.60/1M output tokens — the cheapest OpenAI model with vision capability
- **Native async streaming**: The OpenAI Python SDK (`AsyncOpenAI`) supports true async streaming, so the event loop is never blocked during generation
- **Reliability**: OpenAI's API is mature with well-defined error codes and retry semantics
- **Image detail control**: The `"detail": "low"` setting uses ~85 tokens per image vs ~1000 for `"high"` — a key cost lever

**Alternatives considered:**
- gpt-4o: Higher quality but ~10× more expensive per token. Unnecessary for typical trade show Q&A.
- Gemini 1.5 Flash: Was the original implementation but replaced — the Python SDK doesn't support native async streaming (requires `run_in_executor` workaround), and OpenAI's API better fits the existing TTS stack.
- Local VLM (e.g., LLaVA, Moondream): No API cost, but requires GPU for reasonable speed. Not portable to evaluator's system.

### Latency impact

gpt-4o-mini typically streams the first token in 0.5–1.5 seconds for short prompts. The sentence-by-sentence streaming approach means the user sees the first sentence almost immediately rather than waiting for the full response.

### API failure handling

- Network errors: Caught in `_generate_response`, logged with `step="vision_api"`, client receives `{ event: "error", step: "vision_api" }`
- Rate limiting (429): Same error path; structured log makes it identifiable
- Timeout: `asyncio.wait_for` on frame request (3s); OpenAI streaming has built-in timeout via the SDK

### Image cost control

Only the **last 3 image turns** are included in API calls (`MAX_CONVERSATION_IMAGE_HISTORY=3`). All text history is preserved. Images are sent at `"detail": "low"` (~85 tokens each). A typical turn costs ~200–500 text tokens + ~85 tokens per image.

---

## 3. Audio Pipeline

### Microphone capture (browser)

`navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000 } })` captures mono 16kHz audio. A `ScriptProcessorNode` (512 samples per callback) accumulates samples and sends them over WebSocket.

An `AudioWorklet` (`correlator.worklet.js`) runs alongside to calculate microphone/TTS correlation for **barge-in detection**: processes 480-sample frames at 48kHz, computing signal correlation and RMS for both mic and TTS reference. If `corr > 0.3 && micRms > 0.01` while the bot is speaking, it sends `{ event: "interrupt" }` to the backend and stops local TTS playback immediately. Gracefully degrades if AudioWorklet is unavailable (no echo correlation, barge-in still possible via VAD).

### Speech detection (server)

The server uses a two-stage pipeline:

**Stage 1 — Silero VAD (ONNX)**: Processes each 32ms chunk with a stateful ONNX model. Returns a smoothed probability (0–1). State machine transitions: QUIET → STARTING → SPEAKING → STOPPING.

**Stage 2 — SmartTurn v3 EOU (ONNX)**: When in STOPPING state, this model analyzes up to 8 seconds of recent audio to determine if the utterance is truly complete (vs. a mid-sentence pause). Requires ≥4 seconds of audio and ≥0.9 confidence to confirm end-of-utterance.

This two-stage approach prevents premature turn-taking on mid-sentence pauses, which is the main failure mode of simpler silence-threshold systems.

### Transcription: faster-whisper

`faster-whisper` (CTranslate2-based) runs OpenAI's Whisper model on CPU with int8 quantization. The `base` model (~74MB) achieves ~0.5–1.5s per typical 3–8 second utterance.

**Why not cloud STT (Deepgram, AssemblyAI, Google)?**
- Cost: Cloud STT adds per-minute charges
- Latency: Similar to local for short utterances; adds network RTT
- Offline: Local works without internet
- Cross-platform: faster-whisper works on any CPU with no GPU required

**Thread safety**: `faster-whisper` is thread-safe when called from `run_in_executor`. No global lock is needed.

### Text-to-Speech (TTS)

**Primary:** `edge-tts` (Microsoft Edge TTS, free, no API key required). Voice: `en-US-GuyNeural` (male). Fallback voice: `en-US-ChristopherNeural`.

**Fallback:** OpenAI TTS (`gpt-4o-mini-tts`) when edge-tts fails and `OPENAI_API_KEY` is set.

**Delivery:** Responses are streamed sentence-by-sentence. Each sentence is converted to WAV (MP3 → WAV via pydub) and sent as `{ event: "media", mime: "audio/wav", audio: "<base64>", index: N }`. Index `0` signals the start of a new response and resets the client's playback queue.

**Client playback:** `useTTSPlayback` maintains an ordered WAV queue decoded via the Web Audio API. Chunks play sequentially; `index=0` clears any in-progress audio from the previous response. Browser SpeechSynthesis (`useStreamingSpeech`) is present but disabled due to a Chrome 15-second utterance limit bug.

---

## 4. Frontend Architecture

### Component structure

```
App (root state machine)
├── StatusBar           — connection status, speech state badge
├── MediaControls       — mic and camera toggle buttons (shown when active)
├── [Left panel]
│   ├── VideoPreview    — live webcam feed + YOLO annotation overlay + capture flash
│   ├── AudioVisualizer — VAD probability bar (updates 30fps via state events)
│   ├── StartButton     — Start/Stop toggle
│   └── MetricsDashboard — collapsible panel, SSE-fed latency + health
└── [Right panel]
    └── ConversationThread → MessageBubble[]
```

### Hooks

| Hook | Responsibility |
|---|---|
| `useWebSocket` | Single socket per session, exponential backoff reconnect (1s→10s), event handler registry |
| `useSession` | Session ID generation/retrieval via `sessionStorage` (per-tab, no cross-tab collision) |
| `useAudioPipeline` | Mic capture → AudioWorklet → 512-sample chunks over WebSocket |
| `useTTSPlayback` | WAV queue playback via Web Audio API, ordered by index |
| `useConversation` | Message state: partial → complete (user), streaming → complete (assistant) |
| `useVideoCapture` | Camera stream, on-demand frame capture, 1.5s background scene frame push |
| `useAnnotations` | YOLO bounding boxes on overlay canvas; flips x-coords for mirrored video; clears after 3s |
| `useStreamingSpeech` | Browser SpeechSynthesis wrapper — present but disabled (Chrome 15s bug) |

### Start/Stop flow

1. User clicks "Start Conversation"
2. `startCamera()` and `startListening()` run in parallel (browser permission prompts)
3. `startSceneFramePush()` begins sending frames every 1.5s for YOLO
4. `{ event: "start" }` sent to backend
5. `vadProb` + `speechState` update in real-time via `state` events

Stop: sends `{ event: "stop" }`, stops scene push, releases both media streams, stops TTS playback.

### Chat state management

The `useConversation` hook maintains `Message[]` state. Messages flow through stages:
- **Partial** (user, `partial: true`): shown italic/dimmed, updated in real-time during transcription
- **Complete user** (`complete: true`): replaces partial, full opacity
- **Streaming assistant** (`streaming: true`): appended sentence-by-sentence as the model streams
- **Complete assistant** (`complete: true`): finalized, streaming indicator removed
- On interrupt: active streaming message marked non-streaming immediately

### Video display

The `<video>` element is mirrored horizontally (`transform: scaleX(-1)`) for a natural selfie view. A hidden `<canvas>` captures frames on demand without interrupting playback. An overlay canvas draws YOLO bounding boxes (x-coordinates flipped to match the mirrored video).

### TTS mode

The backend supports two TTS modes set via `{ event: "config", tts_mode: "server"|"client" }`:
- **server** (default): backend generates WAV and streams it over WebSocket
- **client**: backend skips TTS; browser handles speech (currently disabled)

---

## 5. Data Model & Storage

### In-memory conversation format

```typescript
interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
  frame?: string;  // base64 JPEG, null for assistant turns
}
```

Visual context is stored inline with the turn. Only the last `MAX_CONVERSATION_IMAGE_HISTORY=3` frames are sent to the vision API (older turns are text-only in the API request). **Frames are not persisted to disk** — they exist only in the in-memory conversation context during a session.

### Persistent storage (SQLite)

```sql
sessions: id (UUID), title, created_at, updated_at
turns: id, session_id FK, role, content, frame_path (unused, always null),
       stt_latency_ms, llm_first_token_ms, tts_first_audio_ms, created_at
```

The `frame_path` column exists in the schema but is never written — frame storage was removed in favour of keeping inference in-memory only.

### Background scene detection

`SceneDetector` (YOLOv8n) runs stateless in-memory inference on each client-pushed background frame. Results are sent immediately as `{ event: "annotations", boxes: [...] }` to the frontend and used to augment the LLM prompt with scene context. No scene data is written to disk or the database.

### Scaling to hundreds of concurrent conversations

The current architecture would need:
1. **PostgreSQL** (replace SQLite — concurrent writes, connection pooling)
2. **Redis** for session state (replace `app.state.active_sessions` dict)
3. **Horizontal scaling**: VAD/EOU per-session state is stateful — would need sticky sessions or session state pushed to Redis
4. **Whisper worker pool**: dedicated transcription workers with a work queue (Celery/RQ) rather than per-session `run_in_executor`

---

## 6. Observability & Production Readiness

### Structured logging

Every log line includes: timestamp, log level, module name, and step name (e.g., `[transcribe]`, `[response]`, `[openai]`). This makes it possible to grep for a specific step's failures.

Example log trace for one turn:
```
[INFO] pipeline.speech_detector: [state] quiet → starting (vad: 0.312)
[INFO] pipeline.speech_detector: [state] starting → speaking (vad: 0.623)
[INFO] pipeline.speech_detector: [state] speaking → stopping (vad: 0.218)
[INFO] pipeline.speech_detector: [detector] Segment captured (3.84s)
[INFO] pipeline.vision_pipeline: [transcribe] #1: 'What is this?' (843ms)
[INFO] pipeline.vision_pipeline: [pipeline] Frame received (42156 bytes)
[INFO] vision.openai_client: [openai] First chunk in 1.23s
[INFO] pipeline.vision_pipeline: [response] Complete (first_llm=1.23s)
```

### MetricsDashboard

The `MetricsDashboard` frontend component displays real-time observability data sourced from two endpoints:
- `GET /health`: per-component status (vad, transcriber, vision_api, tts, database)
- `GET /dashboard/events` (SSE): streams `turn_complete` events with per-turn STT, LLM first-token, and TTS first-audio latencies, plus active session list

### Health endpoint

`GET /health` returns:
```json
{
  "status": "ok",
  "components": {
    "vad": "ok",
    "transcriber": "ok",
    "vision_api": "ok",
    "tts": "ok",
    "database": "ok"
  },
  "active_sessions": 1,
  "session_ids": ["abc123..."]
}
```

If the vision API is unreachable, `"vision_api": "unreachable"` and `"status": "degraded"`.

### Error identification

Every error response from the server includes a `step` field:
```json
{ "event": "error", "message": "...", "step": "vision_api" }
```

Steps: `websocket`, `transcriber`, `vision_api`, `tts`, `response`

### SLA metrics to track in production

- **End-to-end latency**: speech_end → first assistant text token (target <2s)
- **STT P95 latency**: target <1.5s for 5s utterances
- **Vision API P95 latency**: target <3s
- **WebSocket connection error rate**: target <0.1%
- **OpenAI 429 rate**: indicates rate limit saturation
- **Frame capture timeout rate**: indicates camera/network issues

---

## 7. What Would I Improve?

With two more weeks, in order of priority:

1. **WebRTC for audio**: Replace the `ScriptProcessorNode` WebSocket approach with WebRTC + a lightweight SFU. This would give native echo cancellation, jitter buffer management, and better codec support (Opus). The current approach can have dropouts under heavy CPU load.

2. **Whisper VAD filter**: Re-enable `vad_filter=True` in faster-whisper for cases where the Silero VAD occasionally captures noise segments. This would reduce spurious transcriptions and wasted API calls.

3. **Better error recovery**: The current error handler always yields a generic message. With more time, I'd add retry logic with exponential backoff for transient errors (5xx, timeout) while surfacing permanent errors (invalid key, quota exceeded) clearly.

4. **Frame quality adaptation**: Currently frames are always 640×480 JPEG at quality 0.7. For objects that need fine detail (small text, serial numbers), I'd implement a "zoom mode" that captures a higher-quality crop of the center of the frame.

5. **Session restoration**: The DB stores conversation history, but when the frontend reconnects, it currently only restores text context (not images). With more time, I'd cache the last N frames on the server and include them in the restored context.
