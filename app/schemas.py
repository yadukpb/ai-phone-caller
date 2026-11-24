from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TTSModel(str, Enum):
    QWEN_0_6B = "qwen3-tts-0.6b"
    QWEN_1_7B = "qwen3-tts-1.7b"


class CallStatus(str, Enum):
    QUEUED = "queued"
    DRY_RUN = "dry_run"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    OPTED_OUT = "opted_out"
    CANCELED = "canceled"


class CreateCallRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)
    agent_id: str = Field(default="default-agent", min_length=1, max_length=100)
    tts_model: TTSModel | None = None
    voice_reference: str | None = Field(default=None, max_length=500)
    voice_reference_text: str | None = Field(default=None, max_length=2_000)
    prompt: str = Field(min_length=1, max_length=10_000)
    metadata: dict[str, str] = Field(default_factory=dict)
    campaign_id: str | None = Field(default=None, max_length=100)
    max_attempts: int = Field(default=2, ge=1, le=5)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        if not value.startswith("+") or not value[1:].isdigit():
            raise ValueError("phone_number must use E.164 format, for example +919999999999")
        return value


class CallResponse(BaseModel):
    call_id: str
    status: CallStatus
    phone_number: str
    agent_id: str
    tts_model: TTSModel
    provider: str
    message: str


class UpdateCallStatusRequest(BaseModel):
    status: CallStatus
    provider_call_id: str | None = Field(default=None, max_length=200)


class CreateCampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(default="default-agent", min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=10_000)
    tts_model: TTSModel | None = None
    scheduled_at: str | None = None
    calls_per_minute: int = Field(default=6, ge=1, le=60)


class AddContactRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)
    name: str | None = Field(default=None, max_length=200)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        if not value.startswith("+") or not value[1:].isdigit():
            raise ValueError("phone_number must use E.164 format")
        return value


class TranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=200_000)
    summary: str | None = Field(default=None, max_length=10_000)


class RecordingRequest(BaseModel):
    recording_url: str = Field(min_length=1, max_length=2_000)
    duration_seconds: int | None = Field(default=None, ge=0)


class OptOutRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)
    reason: str | None = Field(default=None, max_length=500)
