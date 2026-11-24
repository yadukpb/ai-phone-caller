from collections.abc import AsyncIterator

import httpx

from .config import Settings
from .schemas import TTSModel


class QwenTTSClient:
    """Client for a local OpenAI-compatible Qwen3-TTS server."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream(
        self,
        text: str,
        model: TTSModel,
        voice_reference: str | None = None,
        voice_reference_text: str | None = None,
    ) -> AsyncIterator[bytes]:
        voice = voice_reference or "default"
        if voice_reference:
            voice = f"{voice_reference}::{voice_reference_text or ''}"
        payload = {
            "model": model.value,
            "input": text,
            "voice": voice,
            "response_format": "pcm",
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.settings.tts_api_key}"} if self.settings.tts_api_key else {}
        url = f"{self.settings.tts_base_url.rstrip('/')}/v1/audio/speech"
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
