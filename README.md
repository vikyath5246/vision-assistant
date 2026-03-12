# Conversational Vision Assistant

A trade show / exhibition demo: visitors point their webcam at products and speak naturally. The assistant identifies what it sees, answers questions, and responds with synthesized voice — all in real time.

## How It Works

```
Microphone → VAD (Silero) → EOU detection (SmartTurn) → Whisper STT
                                                               ↓
Webcam ──────────────────────────────────────────→ OpenAI gpt-4o-mini (vision)
                                                               ↓
                                              edge-tts / OpenAI TTS → Speaker
                                                               ↓
                                                     React chat thread
```

1. Silero VAD (ONNX) detects speech frames in real time
2. SmartTurn EOU model (ONNX) decides when the visitor has finished speaking
3. faster-whisper transcribes the captured segment
4. The current webcam frame + transcript are sent to `gpt-4o-mini`
5. The streamed response is spoken aloud and shown in the chat thread
6. Full conversation history (last 3 frames) is kept in context for follow-ups

## Features

- Real-time VAD + end-of-utterance detection (no push-to-talk)
- Streaming LLM responses — text appears word-by-word
- TTS audio responses (edge-tts primary, OpenAI TTS fallback)
- Conversation memory with visual context across turns
- SQLite session persistence
- Live observability dashboard (SSE metrics stream)
- Optional background scene detection via YOLOv8n

## Requirements

- An [OpenAI API key](https://platform.openai.com/api-keys)
- A webcam and microphone
- Internet connection (for OpenAI API and edge-tts)
- **Docker** (recommended) — or Python 3.10+ and Node.js 18+ for manual setup
- Create an .env file from the example and add your OpenAI API key there.

## Setup

### Docker (recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cd vision-assistant

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env and set your OPENAI_API_KEY

# Build and start both services
docker compose up --build
```

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)

All models (Silero VAD, SmartTurn, faster-whisper, YOLOv8n) are downloaded during the backend image build. The first build takes a few minutes; subsequent builds use the cached layer.

The backend starts first and must pass its `/health` check before the frontend container comes up. The SQLite database is stored in a named Docker volume (`app_data`) so it persists across restarts.

```bash
# Stop
docker compose down

# Stop and wipe the database volume
docker compose down -v
```

---

### Manual Setup

#### Backend

```bash
cd vision-assistant/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY

# Start the backend
python main.py
# Runs on http://localhost:8000
```

> The Silero VAD and SmartTurn ONNX models are downloaded automatically at startup if not present. The faster-whisper `base` model (~74 MB) is also downloaded on first run.

#### Frontend

```bash
cd vision-assistant/frontend

npm install
npm run dev
# Runs on http://localhost:5173
```

Open [http://localhost:5173](http://localhost:5173) in Chrome or Firefox.

## Usage

1. Click **"Start Conversation"** — webcam and microphone activate
2. Point the camera at an iPhone 17 or iPhone 17 Pro
3. Ask a question naturally: *"What chip does this have?"*, *"How much does this cost?"*, *"What's the difference between these two?"*
4. The assistant identifies the device, answers, and speaks the response
5. Ask follow-ups — the assistant remembers the full conversation
6. Click **"Stop Conversation"** to end the session

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Vision model (`gpt-4o-mini` or `gpt-4o`) |
| `WHISPER_MODEL_SIZE` | `base` | STT model size: `tiny` / `base` / `small` |
| `TTS_VOICE` | `en-US-GuyNeural` | Primary edge-tts voice |
| `TTS_FALLBACK_VOICE` | `en-US-ChristopherNeural` | Fallback edge-tts voice |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | OpenAI TTS model (used if edge-tts fails) |
| `OPENAI_TTS_VOICE` | `alloy` | OpenAI TTS voice |
| `ENABLE_OPENAI_TTS_FALLBACK` | `true` | Fall back to OpenAI TTS when edge-tts fails |
| `ENABLE_BACKGROUND_SCENE` | `true` | Enable YOLOv8n background scene detection |
| `DATABASE_URL` | `sqlite:///./vision_assistant.db` | Database connection string |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Component health (VAD, STT, vision API, TTS, DB) |
| `WS` | `/ws/{session_id}` | Main WebSocket — audio/video/text stream |
| `GET` | `/api/sessions` | List all conversation sessions |
| `GET` | `/api/sessions/{id}/turns` | Conversation history for a session |
| `GET` | `/dashboard/events` | SSE stream for real-time observability metrics |

## Project Structure

```
vision-assistant/
├── docker-compose.yml           # Orchestrates backend + frontend containers
├── backend/
│   ├── Dockerfile               # python:3.11-slim, downloads models at build time
│   ├── main.py                  # FastAPI app + startup lifespan
│   ├── config.py                # All configuration constants
│   ├── dependencies.py          # Shared singleton resources
│   ├── download_models.py       # Downloads ONNX + Whisper + YOLO models
│   ├── pipeline/
│   │   ├── vad_detector.py      # Silero VAD + SmartTurn EOU (ONNX)
│   │   ├── audio_buffer.py      # Speech segmentation buffer
│   │   ├── speech_detector.py   # VAD state machine
│   │   ├── transcriber.py       # faster-whisper STT
│   │   ├── vision_pipeline.py   # Per-session orchestrator
│   │   ├── tts_handler.py       # edge-tts + OpenAI TTS fallback
│   │   ├── scene_detector.py    # YOLOv8n background scene detection
│   │   └── scene_state.py       # Scene state management
│   ├── vision/
│   │   └── openai_client.py     # gpt-4o-mini vision client + product catalogue
│   ├── db/                      # SQLAlchemy models + CRUD
│   ├── api/                     # WebSocket, sessions, dashboard endpoints
│   ├── models/                  # ONNX model files (downloaded at build/startup)
│   ├── .env.example             # Environment variable template
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile               # Node 20 builder → nginx:alpine, serves on port 80
│   └── src/
│       ├── hooks/               # useSession, audio pipeline, video capture
│       ├── components/          # ConversationThread, MessageBubble, AudioVisualizer, MetricsDashboard
│       └── workers/             # correlator.worklet.js (AudioWorklet)
├── .gitignore
└── README.md
```

## Extending the Product Catalogue

Edit `PRODUCT_CATALOGUE` in [backend/vision/openai_client.py](backend/vision/openai_client.py). Each entry needs:
- `Visual ID` — how the model identifies the product from the camera feed
- Spec fields the assistant should use when answering questions

## Dependencies

### Backend
| Package | Purpose |
|---|---|
| fastapi | Web framework |
| uvicorn | ASGI server |
| onnxruntime | VAD + EOU inference (Silero, SmartTurn) |
| faster-whisper | Speech-to-text (CPU, cross-platform) |
| transformers | Whisper feature extractor for EOU model |
| openai | gpt-4o-mini vision API + OpenAI TTS |
| Pillow | Image processing |
| edge-tts | Primary TTS (free, no API key) |
| pydub | MP3 → WAV conversion |
| ultralytics | YOLOv8n background scene detection |
| sqlalchemy | Database ORM |
| python-dotenv | Environment variable loading |

### Frontend
| Package | Purpose |
|---|---|
| react 18 | UI framework |
| vite | Build tool + dev server |
| typescript | Type safety |
