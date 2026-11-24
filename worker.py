"""LiveKit outbound phone agent worker.

Run with: python worker.py dev
"""

import ast
import json
import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, inference
from livekit.plugins import openai

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phone-caller-worker")


def read_metadata(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = ast.literal_eval(raw)
    return value if isinstance(value, dict) else {}


def make_tts(model: str, voice_reference: str | None = None, voice_reference_text: str | None = None):
    """Use the local OpenAI-compatible Qwen TTS server."""
    base_url = os.getenv("TTS_BASE_URL", "http://127.0.0.1:8001").rstrip("/") + "/v1"
    api_key = os.getenv("TTS_API_KEY", "local")
    voice = "default"
    if voice_reference:
        voice = f"{voice_reference}::{voice_reference_text or ''}"
    return openai.TTS(model=model, voice=voice, base_url=base_url, api_key=api_key)


async def entrypoint(ctx: agents.JobContext):
    metadata = read_metadata(ctx.job.metadata)
    prompt = metadata.get("prompt", "Be concise, polite, and identify yourself as an AI assistant.")
    model = metadata.get("tts_model", os.getenv("DEFAULT_TTS_MODEL", "qwen3-tts-0.6b"))

    await ctx.connect()
    session = AgentSession(
        stt=inference.STT(model=os.getenv("STT_MODEL", "deepgram/nova-3"), language="en"),
        llm=inference.LLM(model=os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")),
        tts=make_tts(model, metadata.get("voice_reference"), metadata.get("voice_reference_text")),
    )
    await session.start(
        room=ctx.room,
        agent=Agent(instructions=prompt),
        room_input_options=RoomInputOptions(),
    )
    await session.generate_reply(
        instructions="Greet the person, briefly explain the purpose of the call, and ask your first question."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, agent_name=os.getenv("LIVEKIT_AGENT_NAME", "phone-caller")))
