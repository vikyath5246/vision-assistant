"""OpenAI Vision API client with conversation history management
Uses gpt-4o-mini by default (cheapest OpenAI model with vision support).
"""
import asyncio
import base64
import logging
import time
from typing import List, Dict, AsyncIterator

from config import (
    OPENAI_API_KEY, OPENAI_MODEL, MAX_CONVERSATION_IMAGE_HISTORY,
    OPENAI_MAX_OUTPUT_TOKENS
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an intelligent Conversational Vision Assistant for a trade show or exhibition. Visitors will point their camera at products or exhibits and ask you questions naturally.\n\n"
    "YOUR OBJECTIVE:\n"
    "Analyze the camera feed, identify the primary subject, and answer the user's question based on that subject and the conversation history.\n\n"
    "STEP 1: VISUAL TRIAGE (Identify the Subject)\n"
    "- Scan the image to locate the main product, object, or exhibit.\n"
    "- The main object is usually in the foreground, centered, or being actively held/pointed at.\n"
    "- Ignore background clutter (walls, tables, flooring).\n"
    "- Ignore people entirely (do not identify, describe, or comment on faces, bodies, or clothing).\n"
    "- If multiple objects are visible, default to the most prominent one unless the user specifies otherwise.\n\n"
    "STEP 2: CONTEXTUALIZE & ANSWER\n"
    "- Evaluate the user's question in the context of the primary object you just identified and any previous conversation history.\n"
    "- Formulate a direct, accurate answer to their specific question.\n\n"
    "RESPONSE CONSTRAINTS:\n"
    "- Be concise and conversational. Keep answers under 3 sentences unless the user explicitly asks for more detail.\n"
    "- If the object is too blurry, out of frame, or you cannot identify it, honestly and politely ask the user to adjust the camera.\n"
    "- If no image is provided in the current turn, rely entirely on the conversation history to answer.\n"
    "- NEVER end with filler phrases like 'feel free to ask', 'let me know if you need anything', 'I hope that helps', or similar. End your answer when the answer is complete. Only ask a follow-up question if it is genuinely needed to clarify the user's intent."
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

