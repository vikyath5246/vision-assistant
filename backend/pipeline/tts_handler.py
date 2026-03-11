"""Text-to-Speech using edge-tts (Microsoft's free TTS, no API key required)
Outputs MP3 converted to WAV for browser playback compatibility
"""
import asyncio
import io
import logging
from config import (
    OPENAI_API_KEY,
    OPENAI_TTS_MODEL,
    OPENAI_TTS_VOICE,
    TTS_VOICE,
    TTS_RATE,
)

logger = logging.getLogger(__name__)


def _mp3_to_wav(mp3_data: bytes) -> bytes:
    """Convert MP3 bytes to WAV bytes using pydub"""
    from pydub import AudioSegment
    audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
    wav_buf = io.BytesIO()
    audio.export(wav_buf, format="wav")
    return wav_buf.getvalue()


class EdgeTTSHandler:
    """TTS using Microsoft edge-tts - no API key, no model download"""

    def __init__(self, voice: str = TTS_VOICE, rate: str = TTS_RATE):
        self.voice = voice
        self.rate = rate
        self._openai_client = None

        if OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
                logger.info(
                    "OpenAI TTS fallback enabled (model=%s, voice=%s)",
                    OPENAI_TTS_MODEL,
                    OPENAI_TTS_VOICE,
                )
            except Exception as e:
                logger.warning("Failed to initialize OpenAI TTS fallback: %s", e)

        logger.info("EdgeTTS handler initialized (voice=%s)", voice)

    async def _generate_with_edge_tts(self, text: str) -> bytes:
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            mp3_chunks = []

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])

            if not mp3_chunks:
                return b""

            mp3_data = b"".join(mp3_chunks)
            wav_data = await asyncio.get_event_loop().run_in_executor(
                None, _mp3_to_wav, mp3_data
            )
            return wav_data

        except Exception as e:
            logger.warning("[tts] edge-tts failed for text %r: %s", text[:40], e)
            return b""

    async def _generate_with_openai_tts(self, text: str) -> bytes:
        if not self._openai_client:
            return b""

        try:
            response = await self._openai_client.audio.speech.create(
                model=OPENAI_TTS_MODEL,
                voice=OPENAI_TTS_VOICE,
                input=text,
                response_format="wav",
            )

            if getattr(response, "content", None):
                return response.content
            if hasattr(response, "aread"):
                return await response.aread()
            if hasattr(response, "read"):
                return response.read()
            return b""
        except Exception as e:
            logger.error("[tts] OpenAI fallback failed for text %r: %s", text[:40], e)
            return b""

    async def generate_speech_async(self, text: str) -> bytes:
        """Generate WAV audio for text with edge-tts and OpenAI fallback."""
        if not text.strip():
            return b""

        audio = await self._generate_with_edge_tts(text)
        if audio:
            return audio

        return await self._generate_with_openai_tts(text)

    def generate_speech(self, text: str) -> bytes:
        """Synchronous wrapper for use in run_in_executor"""
        return asyncio.run(self.generate_speech_async(text))
