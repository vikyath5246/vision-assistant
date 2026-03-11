"""Gemini Vision API client with conversation history management
Handles multimodal conversations - text + images with cost-controlled history
"""
import asyncio
import base64
import io
import logging
import time
from typing import List, Dict, Optional, AsyncIterator

from config import (
    GEMINI_API_KEY, GEMINI_MODEL, MAX_CONVERSATION_IMAGE_HISTORY,
    GEMINI_MAX_OUTPUT_TOKENS
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful visual assistant at a trade show or exhibition. "
    "The user speaks to you while pointing their camera at products and exhibits. "
    "Analyze what you see in the image and answer their questions concisely. "
    "If no image is provided, respond based on text alone. "
    "Keep answers under 3 sentences unless the user asks for more detail. "
    "If you cannot identify something clearly, say so honestly."
)


class GeminiVisionClient:
    """Client for Gemini 1.5 Flash vision API with conversation history"""

    def __init__(self, api_key: str = GEMINI_API_KEY):
        import google.generativeai as genai
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
        genai.configure(api_key=api_key)
        self._genai = genai
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                temperature=0.7,
            )
        )
        logger.info("Gemini client initialized (model=%s)", GEMINI_MODEL)

    def is_reachable(self) -> bool:
        """Health check: verify Gemini API key is configured and API is accessible.
        Uses list_models (free metadata call) to avoid spending tokens.
        """
        try:
            # list_models is a metadata-only call - doesn't spend tokens
            list(self._genai.list_models())
            return True
        except Exception as e:
            logger.warning("Gemini health check failed: %s", e)
            return False

    def build_contents(self, conversation: List[Dict]) -> List[dict]:
        """Convert internal conversation history to Gemini API format.

        Only the last MAX_CONVERSATION_IMAGE_HISTORY frames are included
        in the API request (cost control). All text history is preserved.
        """
        from PIL import Image

        # Find turns with images; keep only the last N
        image_turn_indices = [
            i for i, turn in enumerate(conversation)
            if turn.get("frame") and turn["role"] == "user"
        ]
        include_image_after = set(image_turn_indices[-MAX_CONVERSATION_IMAGE_HISTORY:])

        contents = []
        for i, turn in enumerate(conversation):
            role = "user" if turn["role"] == "user" else "model"
            parts = []

            if turn["role"] == "user":
                # Include image only for recent turns (token cost control)
                if i in include_image_after and turn.get("frame"):
                    try:
                        img_bytes = base64.b64decode(turn["frame"])
                        img = Image.open(io.BytesIO(img_bytes))
                        parts.append(img)
                    except Exception as e:
                        logger.warning("Failed to decode frame for turn %d: %s", i, e)
                parts.append(turn["content"])
            else:
                parts.append(turn["content"])

            contents.append({"role": role, "parts": parts})

        return contents

    async def generate_streaming(self, conversation: List[Dict]) -> AsyncIterator[str]:
        """Stream raw response chunks as they are produced by the model."""
        contents = self.build_contents(conversation)
        start_time = time.monotonic()

        try:
            # Gemini's Python SDK doesn't natively support async streaming,
            # so we run the synchronous streaming call in a thread executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(contents, stream=True)
            )

            first_chunk = True

            for chunk in response:
                if not chunk.text:
                    continue

                if first_chunk:
                    first_latency = time.monotonic() - start_time
                    logger.info("[gemini] First chunk in %.2fs", first_latency)
                    first_chunk = False

                yield chunk.text

        except Exception as e:
            logger.error("[gemini] Generation error: %s", e, exc_info=True)
            # Surface the error as a message so the user sees something
            yield f"I encountered an error processing your request. Please try again."
            raise

    async def generate(self, conversation: List[Dict]) -> str:
        """Non-streaming generation - returns full response at once"""
        chunks = []
        async for chunk in self.generate_streaming(conversation):
            chunks.append(chunk)
        return "".join(chunks)
