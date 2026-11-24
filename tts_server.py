"""Minimal OpenAI-compatible Qwen3-TTS server.

Run separately in a GPU environment:
  pip install qwen-tts fastapi uvicorn soundfile python-multipart
  python tts_server.py
"""

import io
import os
from functools import lru_cache

import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from qwen_tts import Qwen3TTSModel

app = FastAPI(title="Qwen3-TTS server")


class SpeechRequest(BaseModel):
    model: str = "qwen3-tts-0.6b"
    input: str
    voice: str = "default"
    response_format: str = "wav"
    language: str = "English"
    voice_reference_text: str | None = None


def model_id(model: str, cloned: bool) -> str:
    size = "1.7B" if "1.7b" in model.lower() else "0.6B"
    variant = "Base" if cloned else "CustomVoice"
    return os.getenv(f"QWEN_MODEL_{size}_{variant.upper()}", f"Qwen/Qwen3-TTS-12Hz-{size}-{variant}")


@lru_cache(maxsize=max(1, int(os.getenv("QWEN_MAX_LOADED_MODELS", "1"))))
def load_model(model: str, cloned: bool):
    return Qwen3TTSModel.from_pretrained(model_id(model, cloned), device_map="auto", dtype=torch.bfloat16)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest) -> Response:
    try:
        # The OpenAI-compatible `voice` field is treated as a reference path.
        voice_reference, separator, voice_reference_text = request.voice.partition("::")
        cloned = voice_reference not in {"", "default"} and (request.voice_reference_text or voice_reference_text)
        model = load_model(request.model, bool(cloned))
        if cloned:
            wavs, sample_rate = model.generate_voice_clone(
                text=request.input,
                language=request.language,
                ref_audio=voice_reference,
                ref_text=request.voice_reference_text or voice_reference_text,
            )
        else:
            wavs, sample_rate = model.generate_custom_voice(
                text=request.input,
                language=request.language,
                speaker=os.getenv("QWEN_DEFAULT_SPEAKER", "Ryan"),
            )
        output = io.BytesIO()
        sf.write(output, wavs[0], sample_rate, format="WAV")
        return Response(output.getvalue(), media_type="audio/wav")
    except torch.cuda.OutOfMemoryError as exc:
        fallback = os.getenv("QWEN_FALLBACK_MODEL", "qwen3-tts-0.6b")
        if request.model != fallback:
            load_model.cache_clear()
            try:
                fallback_model = load_model(fallback, bool(cloned))
                if cloned:
                    wavs, sample_rate = fallback_model.generate_voice_clone(
                        text=request.input, language=request.language, ref_audio=voice_reference,
                        ref_text=request.voice_reference_text or voice_reference_text,
                    )
                else:
                    wavs, sample_rate = fallback_model.generate_custom_voice(
                        text=request.input, language=request.language,
                        speaker=os.getenv("QWEN_DEFAULT_SPEAKER", "Ryan"),
                    )
                output = io.BytesIO()
                sf.write(output, wavs[0], sample_rate, format="WAV")
                return Response(output.getvalue(), media_type="audio/wav", headers={"X-TTS-Fallback": fallback})
            except Exception as fallback_exc:
                raise HTTPException(status_code=500, detail=f"TTS OOM and fallback failed: {fallback_exc}") from fallback_exc
        raise HTTPException(status_code=503, detail="TTS model ran out of GPU memory") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
