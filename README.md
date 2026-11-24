# AI Phone Caller

An initial self-hosted foundation for outbound AI phone calls.

## Current slice

- FastAPI control plane for creating outbound call jobs
- Selectable `qwen3-tts-0.6b` and `qwen3-tts-1.7b` models
- Provider-neutral telephony interface
- Qwen TTS streaming adapter that can call a local OpenAI-compatible TTS server
- Safe defaults for opt-outs, call duration, and dry-run development

The telephony and LiveKit workers are intentionally separated from the API so they can be deployed and scaled independently.

## Run locally

```bash
cd ai-phone-caller
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API explorer.

By default the app is in `DRY_RUN=true`, so creating a call job does not contact a carrier.

Set `API_KEY` in `.env` to protect the control plane. Send it as `X-API-Key` on API requests. Keep `DRY_RUN=true` until LiveKit, SIP, and the TTS server have been tested.

## Create a call

```bash
curl -X POST http://127.0.0.1:8000/v1/calls \
  -H 'content-type: application/json' \
  -d '{
    "phone_number": "+919999999999",
    "agent_id": "appointment-agent",
    "tts_model": "qwen3-tts-0.6b",
    "voice_reference": "voices/agent.wav",
    "prompt": "You are calling to confirm an appointment. Be concise and polite."
  }'
```

Inspect calls:

```bash
curl -H 'X-API-Key: your-key' http://127.0.0.1:8000/v1/calls
curl -H 'X-API-Key: your-key' http://127.0.0.1:8000/v1/calls/<call-id>
```

## TTS contract

The API expects a local Qwen3-TTS server exposing an OpenAI-compatible endpoint:

```text
POST ${TTS_BASE_URL}/v1/audio/speech
```

The adapter sends the selected model, input text, voice reference, and `stream=true`. The exact server wrapper can be swapped without changing call logic.

Install GPU TTS dependencies with `pip install -e '.[tts]'`. The API, worker, and TTS process should share `VOICE_DIR` when using voice cloning.

Run checks with:

```bash
python scripts/smoke_check.py
python -m compileall -q app worker.py tts_server.py
```

## Next implementation steps

1. Run `python worker.py dev` to register the LiveKit agent worker.
2. Run `python tts_server.py` in the GPU environment serving Qwen3-TTS (`pip install qwen-tts`).
3. Set `TELEPHONY_PROVIDER=livekit` and configure a LiveKit outbound SIP trunk. LiveKit's documented outbound flow creates a SIP participant in the agent room.
4. Add PostgreSQL/Redis persistence and campaign scheduling for scale.
5. Add consent, opt-out, transfer, voicemail, and recording controls.

Only call people who have consented where required, and clone voices only with permission.
