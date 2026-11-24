from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ai-phone-caller"
    dry_run: bool = True
    database_url: str = "sqlite:///./caller.db"
    tts_base_url: str = "http://127.0.0.1:8001"
    tts_api_key: str = ""
    default_tts_model: str = "qwen3-tts-0.6b"
    max_call_duration_seconds: int = 900
    telephony_provider: str = "none"
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "phone-caller"
    livekit_sip_trunk_id: str = ""
    livekit_from_number: str = ""
    api_key: str = ""
    voice_dir: str = "./voices"
    qwen_max_loaded_models: int = 1
    qwen_fallback_model: str = "qwen3-tts-0.6b"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
