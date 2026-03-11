"""Speech-to-text transcription using faster-whisper (cross-platform CPU)
Replaces mlx-whisper from reference project - same interface, works on any OS
"""
import logging
import numpy as np
from config import WHISPER_MODEL_SIZE, WHISPER_COMPUTE_TYPE, SAMPLE_RATE, MIN_SEGMENT_DURATION

logger = logging.getLogger(__name__)


class FasterWhisperTranscriber:
    """Transcriber using faster-whisper - thread-safe, CPU-based, cross-platform"""

    def __init__(self, model_size: str = WHISPER_MODEL_SIZE):
        from faster_whisper import WhisperModel
        logger.info("Loading faster-whisper model: %s (compute_type=%s)", model_size, WHISPER_COMPUTE_TYPE)
        # device="cpu" + int8 quantization for fast cross-platform inference
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=WHISPER_COMPUTE_TYPE,
            download_root="models/whisper_cache"
        )
        self._model_size = model_size
        logger.info("faster-whisper loaded: %s", model_size)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe float32 mono 16kHz audio to text.
        Thread-safe - faster-whisper handles concurrent calls safely.
        """
        if len(audio) < SAMPLE_RATE * MIN_SEGMENT_DURATION:
            logger.debug("Segment too short (%.2fs), skipping", len(audio) / SAMPLE_RATE)
            return ""

        try:
            segments, _info = self.model.transcribe(
                audio,
                beam_size=1,            # Fastest decoding
                language="en",
                vad_filter=False,       # VAD already handled by Silero upstream
                condition_on_previous_text=False,
                temperature=0.0,        # Deterministic output
                no_speech_threshold=0.6
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text
        except Exception as e:
            logger.error("Transcription error: %s", e, exc_info=True)
            return ""

    @property
    def model_size(self) -> str:
        return self._model_size
