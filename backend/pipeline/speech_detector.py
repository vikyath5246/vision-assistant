"""Speech detection state machine
Extracted from offline-voice-ai/server.py SpeechDetector class
"""
import logging
from typing import List
from enum import Enum

import numpy as np

from config import (
    VAD_START_THRESHOLD, VAD_SPEAKING_THRESHOLD, VAD_STOP_THRESHOLD,
    VAD_QUIET_THRESHOLD, EOU_CONFIDENCE_THRESHOLD, SAMPLE_RATE, ENABLE_TRANSCRIPTION
)
from pipeline.vad_detector import VADDetector, EndOfUtteranceDetector
from pipeline.audio_buffer import AudioBuffer, SpeechState

logger = logging.getLogger(__name__)


class PipelineEvent(str, Enum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    TRANSCRIBE = "transcribe"
    RESPOND = "respond"


class SpeechDetector:
    """Manages VAD state machine and audio segmentation"""

    def __init__(self, vad_model_path: str = None, eou_model_path: str = None):
        from config import VAD_MODEL_PATH, EOU_MODEL_PATH
        self.vad = VADDetector(vad_model_path or VAD_MODEL_PATH)
        self.eou = EndOfUtteranceDetector(eou_model_path or EOU_MODEL_PATH) if ENABLE_TRANSCRIPTION else None
        self.buffer = AudioBuffer()

        self.state = SpeechState.QUIET
        self.is_listening = False
        self.is_responding = False
        self.user_speaking = False

        self.segment_count = 0
        self.current_segment = None

    def start_listening(self):
        self.is_listening = True
        self.segment_count = 0
        self.user_speaking = False
        logger.info("[detector] Started listening")

    def stop_listening(self):
        self.is_listening = False
        self.user_speaking = False
        logger.info("[detector] Stopped (segments: %d)", self.segment_count)

    def process_chunk(self, chunk: np.ndarray) -> List[PipelineEvent]:
        if not self.is_listening:
            return []

        vad_prob = self.vad.process_chunk(chunk)
        self.buffer.add_chunk(chunk, self.state)

        if self.eou:
            self.eou.add_audio(chunk)

        return self._update_state(vad_prob)

    def _update_state(self, vad_prob: float) -> List[PipelineEvent]:
        events = []
        prev_state = self.state

        if self.state == SpeechState.QUIET:
            if vad_prob >= VAD_START_THRESHOLD:
                self.state = SpeechState.STARTING
                self.user_speaking = True
                events.append(PipelineEvent.SPEECH_START)

        elif self.state == SpeechState.STARTING:
            if vad_prob >= VAD_SPEAKING_THRESHOLD:
                self.state = SpeechState.SPEAKING
            elif vad_prob < VAD_QUIET_THRESHOLD:
                self.state = SpeechState.QUIET
                self.user_speaking = False

        elif self.state == SpeechState.SPEAKING:
            if vad_prob < VAD_STOP_THRESHOLD:
                self.state = SpeechState.STOPPING
                self.current_segment = self.buffer.get_segment()
                if self.current_segment is not None:
                    logger.info(
                        "[detector] Segment captured (%.2fs)",
                        len(self.current_segment) / SAMPLE_RATE
                    )
                    events.append(PipelineEvent.TRANSCRIBE)

        elif self.state == SpeechState.STOPPING:
            vad_quiet = vad_prob < VAD_QUIET_THRESHOLD

            eou_confirms = not self.eou
            if self.eou and vad_quiet and self.eou.has_enough_audio():
                result = self.eou.detect()
                eou_confirms = result['ended'] and result['confidence'] > EOU_CONFIDENCE_THRESHOLD
                if eou_confirms:
                    logger.info("[detector] EOU confirmed (conf: %.2f)", result['confidence'])

            if vad_quiet and eou_confirms:
                self.state = SpeechState.QUIET
                events.append(PipelineEvent.SPEECH_END)

                if self.user_speaking:
                    events.append(PipelineEvent.RESPOND)
                    self.user_speaking = False

                if self.eou:
                    self.eou.reset()
                self.current_segment = None

            elif vad_prob > VAD_SPEAKING_THRESHOLD:
                self.state = SpeechState.SPEAKING
                self.current_segment = None

        if prev_state != self.state:
            logger.info("[state] %s → %s (vad: %.3f)", prev_state.value, self.state.value, vad_prob)

        return events

    def get_state(self) -> dict:
        vad_value = float(self.vad.smoothed_prob)
        return {
            'state': self.state.value,
            'vad_prob': vad_value,
            'segments': self.segment_count,
            'listening': self.is_listening,
            'responding': self.is_responding
        }
