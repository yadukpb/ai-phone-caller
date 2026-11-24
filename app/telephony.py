import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .schemas import CallStatus, CreateCallRequest, TTSModel
from .store import CallStore


@dataclass(slots=True)
class CallJob:
    call_id: str
    request: CreateCallRequest
    tts_model: TTSModel
    status: CallStatus


class TelephonyGateway:
    """Carrier boundary; LiveKit/Twilio/Telnyx implementations plug in here."""

    def __init__(self, settings: Settings, store: CallStore) -> None:
        self.settings = settings
        self.store = store

    async def create_outbound_call(self, request: CreateCallRequest) -> CallJob:
        self._validate_voice_reference(request.voice_reference)
        model = request.tts_model or TTSModel(self.settings.default_tts_model)
        if self.store.is_opted_out(request.phone_number):
            raise ValueError("This phone number is opted out")
        status = CallStatus.DRY_RUN if self.settings.dry_run else CallStatus.QUEUED
        job = CallJob(call_id=str(uuid4()), request=request, tts_model=model, status=status)
        self.store.create(job.call_id, request, model, status)
        if not self.settings.dry_run and self.settings.telephony_provider == "livekit":
            await self._start_livekit_call(job)
        return job

    def _validate_voice_reference(self, reference: str | None) -> None:
        if not reference:
            return
        root = Path(self.settings.voice_dir).resolve()
        candidate = Path(reference).resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError("voice_reference must be inside VOICE_DIR")
        if not candidate.is_file():
            raise ValueError("voice_reference file does not exist")

    async def _start_livekit_call(self, job: CallJob) -> None:
        if not all((self.settings.livekit_url, self.settings.livekit_api_key,
                    self.settings.livekit_api_secret, self.settings.livekit_sip_trunk_id)):
            self.store.update_status(job.call_id, CallStatus.FAILED)
            raise ValueError("LiveKit configuration is incomplete")
        try:
            from livekit import api
        except ImportError as exc:
            self.store.update_status(job.call_id, CallStatus.FAILED)
            raise ValueError("Install livekit-api to place live calls") from exc

        room_name = f"call-{job.call_id}"
        metadata = {
            "call_id": job.call_id,
            "phone_number": job.request.phone_number,
            "agent_id": job.request.agent_id,
            "tts_model": job.tts_model.value,
            "voice_reference": job.request.voice_reference or "",
            "voice_reference_text": job.request.voice_reference_text or "",
            "prompt": job.request.prompt,
        }
        async with api.LiveKitAPI(self.settings.livekit_url, self.settings.livekit_api_key,
                                  self.settings.livekit_api_secret) as lk:
            await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=self.settings.livekit_agent_name,
                    room=room_name,
                    metadata=json.dumps(metadata),
                )
            )
            participant = await lk.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=self.settings.livekit_sip_trunk_id,
                    sip_call_to=job.request.phone_number,
                    sip_number=self.settings.livekit_from_number,
                    room_name=room_name,
                    participant_identity=f"callee-{job.call_id}",
                    participant_name="Phone Caller",
                    participant_metadata=json.dumps(metadata),
                    wait_until_answered=False,
                )
            )
        self.store.update_status(job.call_id, CallStatus.STARTING, getattr(participant, "participant_id", None))

    def update_status(self, call_id: str, status: CallStatus, provider_call_id: str | None = None) -> None:
        if self.store.get(call_id) is None:
            raise ValueError("Call not found")
        self.store.update_status(call_id, status, provider_call_id)
