# Conversational Vision Assistant

A voice-powered visual Q&A system: speak naturally while pointing your webcam at objects, and the assistant analyzes what it sees and responds in a real-time chat thread.

## Features

- **Tier 1 (Core)**: Live webcam feed + microphone capture, VAD-based speech detection, Whisper transcription, OpenAI vision responses in chat thread
- **Tier 2**: Conversation memory with visual context, TTS audio responses, SQLite persistence, real-time observability dashboard
- **Tier 3**: Streaming text responses word-by-word, multi-session support

## Requirements

- Python 3.10+
- Node.js 18+
- An [OpenAI API key](https://platform.openai.com/api-keys)
- A webcam and microphone
- Internet connection (for OpenAI API and edge-tts)

## Setup

### Backend

```bash
cd vision-assistant/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Pre-download the Whisper model (~74MB, cached for future runs)
python download_models.py

# Start the backend
python main.py
# Backend runs on http://localhost:8000
```

### Frontend

```bash
cd vision-assistant/frontend

npm install
npm run dev
# Frontend runs on http://localhost:5173
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

## Usage

1. Open the app in your browser
2. Click **"Start Conversation"** — webcam and microphone activate
3. Speak while pointing the camera at objects
4. The system transcribes your speech, captures the current video frame, and responds in the chat thread
5. Ask follow-up questions — the assistant remembers the full conversation
6. Click **"Stop Conversation"** to end

## Dependencies

### Backend
| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.109.0 | Web framework |
| uvicorn | 0.27.0 | ASGI server |
| websockets | 12.0 | WebSocket support |
| onnxruntime | 1.16.3 | VAD + EOU inference (cross-platform) |
| transformers | 4.37.2 | Whisper feature extractor for EOU model |
| faster-whisper | 1.0.3 | Speech-to-text (CPU, cross-platform) |
| openai | >=1.30.0 | OpenAI vision API (gpt-4o-mini) |
| Pillow | 10.3.0 | Image processing for vision API |
| edge-tts | 6.1.9 | Text-to-speech (free, no API key) |
| pydub | 0.25.1 | MP3→WAV conversion |
| sqlalchemy | 2.0.29 | Database ORM |
| python-dotenv | 1.0.0 | Environment variable loading |

### Frontend
| Package | Version | Purpose |
|---|---|---|
| react | 18.2 | UI framework |
| vite | 5.1 | Build tool + dev server |
| typescript | 5.3 | Type safety |

## Project Structure

```
vision-assistant/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # All configuration constants
│   ├── dependencies.py      # Shared singleton resources
│   ├── pipeline/
│   │   ├── vad_detector.py  # Silero VAD + SmartTurn EOU (ONNX)
│   │   ├── audio_buffer.py  # Speech segmentation buffer
│   │   ├── speech_detector.py # VAD state machine
│   │   ├── transcriber.py   # faster-whisper STT
│   │   ├── vision_pipeline.py # Per-session orchestrator
│   │   └── tts_handler.py   # edge-tts TTS
│   ├── vision/
│   │   └── openai_client.py # OpenAI gpt-4o-mini vision client
│   ├── db/                  # SQLAlchemy models + CRUD
│   ├── api/                 # WebSocket, sessions, dashboard endpoints
│   ├── models/              # ONNX model files (silero_vad, smart_turn_v3)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── hooks/           # useWebSocket, useAudioPipeline, useVideoCapture, etc.
│       ├── components/      # React UI components
│       └── types/           # TypeScript message interfaces
├── README.md
└── ARCHITECTURE.md
```

## API Endpoints

- `GET /health` — Component health status (VAD, transcriber, vision API, TTS, DB)
- `WS /ws/{session_id}` — Main WebSocket for audio/video/text stream
- `GET /api/sessions` — List all conversation sessions
- `GET /api/sessions/{id}/turns` — Get conversation history for a session
- `GET /dashboard/events` — SSE stream for real-time observability metrics

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model (gpt-4o-mini or gpt-4o) |
| `WHISPER_MODEL_SIZE` | `base` | STT model size: tiny/base/small |
| `TTS_VOICE` | `en-US-AriaNeural` | edge-tts voice |
| `DATABASE_URL` | `sqlite:///./vision_assistant.db` | Database connection string |

## Assumptions

- The evaluator's system has internet access (required for OpenAI API and edge-tts)
- The faster-whisper model downloads automatically on first run (~74MB for `base`)
- The browser is Chrome or Firefox (for WebSocket + AudioWorklet support)
- HTTPS is not required for localhost development (getUserMedia works on localhost without HTTPS)

## Error Handling

- **Camera unavailable**: Error displayed in UI; text-only mode continues
- **OpenAI API error**: Error shown in chat with step identification (`vision_api`)
- **Rate limiting (429)**: Logged with step name; user sees "error" event in chat
- **WebSocket disconnect**: Automatic reconnect with exponential backoff
- **Empty speech**: Ignored (VAD filters below threshold)
- **Model download failure**: Logged with instructions to run `download_models.py`
