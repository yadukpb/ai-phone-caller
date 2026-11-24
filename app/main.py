import asyncio
import json
from uuid import uuid4
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .schemas import (AddContactRequest, CallResponse, CallStatus, CreateCallRequest,
                      CreateCampaignRequest, OptOutRequest, RecordingRequest,
                      TranscriptRequest, TTSModel, UpdateCallStatusRequest)
from .telephony import TelephonyGateway
from .store import CallStore

settings = get_settings()
store = CallStore(settings.database_url)
gateway = TelephonyGateway(settings, store)
app = FastAPI(title=settings.app_name, version="0.2.0")


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "dry_run": settings.dry_run}


@app.post("/v1/calls", response_model=CallResponse, status_code=202, dependencies=[Depends(require_api_key)])
async def create_call(request: CreateCallRequest) -> CallResponse:
    try:
        job = await gateway.create_outbound_call(request)
    except ValueError as exc:
        status = 409 if "opted out" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    message = (
        "Dry run accepted; no carrier call was placed."
        if settings.dry_run
        else "Call queued for the telephony worker."
    )
    return CallResponse(
        call_id=job.call_id,
        status=job.status,
        phone_number=request.phone_number,
        agent_id=request.agent_id,
        tts_model=job.tts_model,
        provider=settings.telephony_provider,
        message=message,
    )


@app.get("/v1/calls", dependencies=[Depends(require_api_key)])
async def list_calls(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> list[dict]:
    return store.list(limit=limit, offset=offset)


@app.get("/v1/calls/{call_id}", dependencies=[Depends(require_api_key)])
async def get_call(call_id: str) -> dict:
    call = store.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@app.patch("/v1/calls/{call_id}/status", dependencies=[Depends(require_api_key)])
async def update_call_status(call_id: str, request: UpdateCallStatusRequest) -> dict:
    try:
        gateway.update_status(call_id, request.status, request.provider_call_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return store.get(call_id) or {}


@app.post("/v1/campaigns", dependencies=[Depends(require_api_key)])
async def create_campaign(request: CreateCampaignRequest) -> dict:
    campaign_id = str(uuid4())
    model = request.tts_model or TTSModel(settings.default_tts_model)
    store.create_campaign(campaign_id, request, model)
    return store.get_campaign(campaign_id) or {"campaign_id": campaign_id}


@app.get("/v1/campaigns", dependencies=[Depends(require_api_key)])
async def list_campaigns() -> list[dict]:
    return store.list_campaigns()


@app.get("/v1/campaigns/{campaign_id}", dependencies=[Depends(require_api_key)])
async def get_campaign(campaign_id: str) -> dict:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign["contacts"] = store.list_contacts(campaign_id)
    return campaign


@app.post("/v1/campaigns/{campaign_id}/contacts", dependencies=[Depends(require_api_key)])
async def add_contact(campaign_id: str, request: AddContactRequest) -> dict:
    if store.get_campaign(campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if store.is_opted_out(request.phone_number):
        raise HTTPException(status_code=409, detail="Contact is opted out")
    contact_id = str(uuid4())
    store.add_contact(contact_id, campaign_id, request)
    return {"contact_id": contact_id, "campaign_id": campaign_id, "status": "pending"}


async def _run_campaign(campaign_id: str) -> None:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        return
    store.update_campaign_status(campaign_id, "running")
    interval = 60 / campaign["calls_per_minute"]
    for contact in store.list_contacts(campaign_id):
        if store.get_campaign(campaign_id)["status"] == "paused":
            break
        if contact["status"] != "pending" or store.is_opted_out(contact["phone_number"]):
            continue
        request = CreateCallRequest(
            phone_number=contact["phone_number"], agent_id=campaign["agent_id"],
            prompt=campaign["prompt"], tts_model=campaign["tts_model"],
            campaign_id=campaign_id, metadata=json.loads(contact["metadata"]),
        )
        try:
            await gateway.create_outbound_call(request)
            store.mark_contact(campaign_id, contact["phone_number"], "called")
        except ValueError:
            store.mark_contact(campaign_id, contact["phone_number"], "failed")
        await asyncio.sleep(interval)
    current = store.get_campaign(campaign_id)
    if current and current["status"] != "paused":
        store.update_campaign_status(campaign_id, "completed")


@app.post("/v1/campaigns/{campaign_id}/run", dependencies=[Depends(require_api_key)])
async def run_campaign(campaign_id: str, background_tasks: BackgroundTasks) -> dict:
    if store.get_campaign(campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    store.update_campaign_status(campaign_id, "queued")
    background_tasks.add_task(_run_campaign, campaign_id)
    return {"campaign_id": campaign_id, "status": "queued"}


@app.post("/v1/campaigns/{campaign_id}/pause", dependencies=[Depends(require_api_key)])
async def pause_campaign(campaign_id: str) -> dict:
    if store.get_campaign(campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    store.update_campaign_status(campaign_id, "paused")
    return {"campaign_id": campaign_id, "status": "paused"}


@app.post("/v1/opt-outs", dependencies=[Depends(require_api_key)])
async def opt_out(request: OptOutRequest) -> dict[str, str]:
    store.opt_out(request.phone_number, request.reason)
    return {"phone_number": request.phone_number, "status": "opted_out"}


@app.post("/v1/calls/{call_id}/transcript", dependencies=[Depends(require_api_key)])
async def attach_transcript(call_id: str, request: TranscriptRequest) -> dict:
    if store.get(call_id) is None:
        raise HTTPException(status_code=404, detail="Call not found")
    store.attach_transcript(call_id, request.transcript, request.summary)
    return store.get(call_id) or {}


@app.post("/v1/calls/{call_id}/recording", dependencies=[Depends(require_api_key)])
async def attach_recording(call_id: str, request: RecordingRequest) -> dict:
    if store.get(call_id) is None:
        raise HTTPException(status_code=404, detail="Call not found")
    store.attach_recording(call_id, request.recording_url, request.duration_seconds)
    return store.get(call_id) or {}


# Keep the operator dashboard in the same deployment as the control plane.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
