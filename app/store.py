import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .schemas import CallStatus, CreateCallRequest, TTSModel


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CallStore:
    def __init__(self, database_url: str) -> None:
        path = database_url.removeprefix("sqlite:///")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calls (
                call_id TEXT PRIMARY KEY, phone_number TEXT NOT NULL, agent_id TEXT NOT NULL,
                tts_model TEXT NOT NULL, voice_reference TEXT, voice_reference_text TEXT,
                prompt TEXT NOT NULL, metadata TEXT NOT NULL, status TEXT NOT NULL,
                provider_call_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                campaign_id TEXT, attempt INTEGER NOT NULL DEFAULT 1, transcript TEXT,
                summary TEXT, recording_url TEXT, duration_seconds INTEGER)""")
            db.execute("""CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY, name TEXT NOT NULL, agent_id TEXT NOT NULL,
                prompt TEXT NOT NULL, tts_model TEXT NOT NULL, scheduled_at TEXT,
                calls_per_minute INTEGER NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS contacts (
                contact_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, phone_number TEXT NOT NULL,
                name TEXT, metadata TEXT NOT NULL, status TEXT NOT NULL,
                UNIQUE(campaign_id, phone_number))""")
            db.execute("""CREATE TABLE IF NOT EXISTS opt_outs (
                phone_number TEXT PRIMARY KEY, reason TEXT, created_at TEXT NOT NULL)""")
            existing = {row[1] for row in db.execute("PRAGMA table_info(calls)").fetchall()}
            for column, definition in {
                "campaign_id": "TEXT",
                "attempt": "INTEGER NOT NULL DEFAULT 1",
                "transcript": "TEXT",
                "summary": "TEXT",
                "recording_url": "TEXT",
                "duration_seconds": "INTEGER",
            }.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE calls ADD COLUMN {column} {definition}")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        return db

    def create(self, call_id: str, request: CreateCallRequest, model: TTSModel, status: CallStatus) -> None:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute("""INSERT INTO calls
                (call_id, phone_number, agent_id, tts_model, voice_reference,
                 voice_reference_text, prompt, metadata, status, provider_call_id,
                 created_at, updated_at, campaign_id, attempt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (call_id, request.phone_number, request.agent_id, model.value, request.voice_reference,
                 request.voice_reference_text, request.prompt, json.dumps(request.metadata), status.value,
                 None, now, now, request.campaign_id, 1))

    def update_status(self, call_id: str, status: CallStatus, provider_call_id: str | None = None) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE calls SET status=?, provider_call_id=COALESCE(?, provider_call_id), updated_at=? WHERE call_id=?",
                       (status.value, provider_call_id, utc_now(), call_id))

    def get(self, call_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM calls WHERE call_id=?", (call_id,)).fetchone()
            return self._decode(dict(row)) if row else None

    def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM calls ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [self._decode(dict(row)) for row in rows]

    @staticmethod
    def _decode(item: dict) -> dict:
        if isinstance(item.get("metadata"), str):
            try:
                item["metadata"] = json.loads(item["metadata"])
            except json.JSONDecodeError:
                item["metadata"] = {}
        return item

    def create_campaign(self, campaign_id: str, request, model: TTSModel) -> None:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (campaign_id, request.name, request.agent_id, request.prompt, model.value,
                        request.scheduled_at, request.calls_per_minute, "draft", now, now))

    def get_campaign(self, campaign_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
            return dict(row) if row else None

    def list_campaigns(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()]

    def update_campaign_status(self, campaign_id: str, status: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE campaigns SET status=?, updated_at=? WHERE campaign_id=?", (status, utc_now(), campaign_id))

    def add_contact(self, contact_id: str, campaign_id: str, request) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO contacts VALUES (?, ?, ?, ?, ?, ?)",
                       (contact_id, campaign_id, request.phone_number, request.name, json.dumps(request.metadata), "pending"))

    def list_contacts(self, campaign_id: str) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM contacts WHERE campaign_id=?", (campaign_id,)).fetchall()]

    def mark_contact(self, campaign_id: str, phone_number: str, status: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE contacts SET status=? WHERE campaign_id=? AND phone_number=?", (status, campaign_id, phone_number))

    def is_opted_out(self, phone_number: str) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM opt_outs WHERE phone_number=?", (phone_number,)).fetchone() is not None

    def opt_out(self, phone_number: str, reason: str | None) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO opt_outs VALUES (?, ?, ?)", (phone_number, reason, utc_now()))

    def attach_transcript(self, call_id: str, transcript: str, summary: str | None) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE calls SET transcript=?, summary=?, updated_at=? WHERE call_id=?", (transcript, summary, utc_now(), call_id))

    def attach_recording(self, call_id: str, url: str, duration: int | None) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE calls SET recording_url=?, duration_seconds=?, updated_at=? WHERE call_id=?", (url, duration, utc_now(), call_id))
