"""General-purpose WhatsApp tool — proxy to Shelly bot for read + write."""

import os

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")
SHELLY_URL = os.environ.get("SHELLY_URL", "http://37.27.191.4:8100")
SHELLY_KEY = os.environ.get("SHELLY_KEY", "shelly-dev-key-change-me")

SHELLY_TIMEOUT = 30.0


def verify_api_key(x_pp_key: str = Header(...)):
    if x_pp_key != PP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def _shelly_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Forward a request to the Shelly WhatsApp bot."""
    async with httpx.AsyncClient(timeout=SHELLY_TIMEOUT) as client:
        try:
            resp = await client.request(
                method,
                f"{SHELLY_URL}{path}",
                headers={"X-Shelly-Key": SHELLY_KEY},
                **kwargs,
            )
            resp.raise_for_status()
            return resp
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Shelly bot unreachable")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Shelly bot timeout")


# --- Models ---


class SendMessage(BaseModel):
    chat_name: str
    message: str


class WhatsAppMessage(BaseModel):
    sender: str
    text: str
    timestamp: str


class HealthStatus(BaseModel):
    ok: bool
    session_active: bool
    detail: str | None = None


# --- Endpoints ---


@router.post("/send")
async def send_message(body: SendMessage, _key: str = Depends(verify_api_key)):
    resp = await _shelly_request("POST", "/send", json=body.model_dump())
    return resp.json()


@router.get("/messages", response_model=list[WhatsAppMessage])
async def get_messages(
    chat_name: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    after: str | None = Query(None, description="ISO timestamp"),
    _key: str = Depends(verify_api_key),
):
    params = {"chat_name": chat_name, "limit": limit}
    if after:
        params["after"] = after
    resp = await _shelly_request("GET", "/messages", params=params)
    return resp.json()


@router.get("/health", response_model=HealthStatus)
async def health(_key: str = Depends(verify_api_key)):
    try:
        resp = await _shelly_request("GET", "/health")
        return resp.json()
    except HTTPException:
        return HealthStatus(ok=False, session_active=False, detail="Shelly unreachable")
