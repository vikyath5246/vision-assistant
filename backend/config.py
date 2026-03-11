"""Configuration constants for the vision assistant"""
import os
from dotenv import load_dotenv

load_dotenv()

# Audio Configuration
SAMPLE_RATE = 16000
CHUNK_SIZE = 512  # 32ms at 16kHz
CHANNELS = 1

# VAD Configuration (tuned values from offline-voice-ai)
VAD_ALPHA = 0.1
VAD_START_THRESHOLD = 0.3
VAD_SPEAKING_THRESHOLD = 0.5
VAD_STOP_THRESHOLD = 0.3
VAD_QUIET_THRESHOLD = 0.05
VAD_STATE_SHAPE = (2, 1, 128)
VAD_CONTEXT_SIZE = 64

# Speech Segmentation
SAFETY_CHUNKS_BEFORE = 4

# End-of-Utterance Detection
EOU_MIN_SAMPLES = 4 * SAMPLE_RATE
EOU_OPTIMAL_SAMPLES = 8 * SAMPLE_RATE
EOU_CONFIDENCE_THRESHOLD = 0.9

# Processing Configuration
MAX_TRANSCRIPTION_QUEUE_SIZE = 8
MIN_SEGMENT_DURATION = 0.3

# LLM Streaming Configuration
LLM_SENTENCE_DELIMITERS = ".!?"

# Model Paths
VAD_MODEL_PATH = "models/silero_vad.onnx"
EOU_MODEL_PATH = "models/smart_turn_v3.onnx"

# STT (faster-whisper)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_COMPUTE_TYPE = "int8"  # CPU-optimized

# OpenAI Vision API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # cheapest model with vision support
MAX_CONVERSATION_IMAGE_HISTORY = 3  # Max frames kept in context (cost control)
OPENAI_MAX_OUTPUT_TOKENS = 512

# TTS
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = os.getenv("TTS_RATE", "+0%")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vision_assistant.db")

# Feature flags
ENABLE_TRANSCRIPTION = True
ENABLE_TTS = True

# Background scene processing (YOLOv8n)
ENABLE_BACKGROUND_SCENE = os.getenv("ENABLE_BACKGROUND_SCENE", "true").lower() == "true"
SCENE_CONFIDENCE_THRESHOLD = float(os.getenv("SCENE_CONFIDENCE_THRESHOLD", "0.5"))
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolov8n.pt")
