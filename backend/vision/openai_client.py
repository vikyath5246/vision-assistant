"""OpenAI Vision API client with conversation history management
Uses gpt-4o-mini by default (cheapest OpenAI model with vision support).
Identical interface to the previous Gemini client so vision_pipeline.py is unchanged.
"""
import asyncio
import base64
import logging
import time
from typing import List, Dict, Optional, AsyncIterator

from config import (
    OPENAI_API_KEY, OPENAI_MODEL, MAX_CONVERSATION_IMAGE_HISTORY,
    OPENAI_MAX_OUTPUT_TOKENS
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a product and exhibit assistant at a trade show or exhibition. "
    "Visitors hold up or point their camera at products and exhibits to ask questions about them.\n\n"
    "FOCUS RULES:\n"
    "- Focus ONLY on the main product, object, or exhibit being intentionally shown or held in the foreground.\n"
    "- IGNORE people entirely — do not describe, comment on, or identify any person, their face, clothing, or body.\n"
    "- IGNORE background elements — walls, tables, flooring, other visitors, signage, or anything not being deliberately presented.\n"
    "- If multiple objects are visible, focus on the one closest to the camera or most prominently featured.\n\n"
    "RESPONSE RULES:\n"
    "- Answer the user's question about the product or exhibit concisely.\n"
    "- Keep answers under 3 sentences unless the user asks for more detail.\n"
    "- If you cannot identify the product or object clearly, say so honestly.\n"
    "- If no image is provided, respond based on the conversation context alone."
)


class OpenAIVisionClient:
    """Client for OpenAI vision API (gpt-4o-mini) with conversation history"""

    def __init__(self, api_key: str = OPENAI_API_KEY):
        from openai import AsyncOpenAI
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env file.")
        self._client = AsyncOpenAI(api_key=api_key)
        self._sync_client = None  # Created lazily for health check
        self._api_key = api_key
        logger.info("OpenAI client initialized (model=%s)", OPENAI_MODEL)

    def is_reachable(self) -> bool:
        """Health check: verify OpenAI API key is valid and API is accessible.
        Uses the models list endpoint (no token cost).
        """
        try:
            from openai import OpenAI
            if self._sync_client is None:
                self._sync_client = OpenAI(api_key=self._api_key)
            self._sync_client.models.list()
            return True
        except Exception as e:
            logger.warning("OpenAI health check failed: %s", e)
            return False

    def build_messages(self, conversation: List[Dict]) -> List[dict]:
        """Convert internal conversation history to OpenAI chat messages format.

        Only the last MAX_CONVERSATION_IMAGE_HISTORY frames are included (cost control).
        All text history is preserved.
        """
        # Find turns with images; keep only the last N
        image_turn_indices = [
            i for i, turn in enumerate(conversation)
            if turn.get("frame") and turn["role"] == "user"
        ]
        include_image_after = set(image_turn_indices[-MAX_CONVERSATION_IMAGE_HISTORY:])

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for i, turn in enumerate(conversation):
            role = turn["role"]  # "user" or "assistant"

            if role == "user":
                content: list = []

                # Include image only for recent turns
                if i in include_image_after and turn.get("frame"):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{turn['frame']}",
                            "detail": "low"  # "low" uses ~85 tokens vs ~1000 for "high"
                        }
                    })

                content.append({"type": "text", "text": turn["content"]})
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "assistant", "content": turn["content"]})

        return messages

    async def generate_streaming(self, conversation: List[Dict]) -> AsyncIterator[str]:
        """Stream raw response chunks as they are produced by the model."""
        messages = self.build_messages(conversation)
        start_time = time.monotonic()

        try:
            stream = await self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=OPENAI_MAX_OUTPUT_TOKENS,
                temperature=0.7,
                stream=True,
            )

            first_chunk = True

            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if not delta:
                    continue

                if first_chunk:
                    logger.info("[openai] First chunk in %.2fs", time.monotonic() - start_time)
                    first_chunk = False

                yield delta

        except Exception as e:
            logger.error("[openai] Generation error: %s", e, exc_info=True)
            yield "I encountered an error processing your request. Please try again."
            raise

    async def generate(self, conversation: List[Dict]) -> str:
        """Non-streaming generation - returns full response at once"""
        chunks = []
        async for chunk in self.generate_streaming(conversation):
            chunks.append(chunk)
        return "".join(chunks)
