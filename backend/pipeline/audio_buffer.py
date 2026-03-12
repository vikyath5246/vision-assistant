"""Audio buffer for speech segments
Ported verbatim from offline-voice-ai/audio_buffer.py
"""
import numpy as np
from typing import Optional, List
from enum import Enum
from config import CHUNK_SIZE, SAMPLE_RATE, SAFETY_CHUNKS_BEFORE


class SpeechState(Enum):
    QUIET = "quiet"
    STARTING = "starting"
    SPEAKING = "speaking"
    STOPPING = "stopping"


class AudioBuffer:
    """Manages audio buffering with safety margins"""

    def __init__(self):
        self.pre_buffer: List[np.ndarray] = []
        self.active_segment: List[np.ndarray] = []
        self.is_capturing = False

    def add_chunk(self, chunk: np.ndarray, state: SpeechState):
        """Add chunk based on state"""
        chunk = chunk.copy()

        if state == SpeechState.QUIET:
            self.pre_buffer.append(chunk)
            if len(self.pre_buffer) > SAFETY_CHUNKS_BEFORE:
                self.pre_buffer.pop(0)

        elif state == SpeechState.STARTING:
            if not self.is_capturing:
                self.is_capturing = True
                self.active_segment = self.pre_buffer.copy()
            self.active_segment.append(chunk)
            self.pre_buffer.append(chunk)
            if len(self.pre_buffer) > SAFETY_CHUNKS_BEFORE:
                self.pre_buffer.pop(0)

        elif state == SpeechState.SPEAKING:
            self.active_segment.append(chunk)

        elif state == SpeechState.STOPPING:
            self.active_segment.append(chunk)

    def get_segment(self) -> Optional[np.ndarray]:
        if not self.active_segment:
            return None
        segment = np.concatenate(self.active_segment)
        self.active_segment = []
        self.is_capturing = False
        return segment


def split_audio_into_chunks(audio: np.ndarray, chunk_size: int = CHUNK_SIZE) -> List[np.ndarray]:
    num_chunks = len(audio) // chunk_size
    return [audio[i * chunk_size:(i + 1) * chunk_size] for i in range(num_chunks)]
