"""House decision API — state machine with JSON file storage."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from backend.house_scraper import scrape_move_nl

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HOUSES_FILE = DATA_DIR / "pp_houses.json"

PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")

# Internal base URL for tool calls (localhost since same server)
TOOLS_BASE = "http://127.0.0.1:8000/api/tools"

# Configurable buying agent email for the email trigger
BUYING_AGENT_EMAIL = os.environ.get("BUYING_AGENT_EMAIL", "")
WHATSAPP_GROUP_NAME = os.environ.get("WHATSAPP_GROUP_NAME", "")

VALID_STATES = {"new", "sent_to_gf", "approved", "booked", "rejected"}
# Valid transitions: from_state -> set of allowed to_states
STATE_TRANSITIONS = {
    "new": {"sent_to_gf", "rejected"},
    "sent_to_gf": {"approved", "rejected"},
    "approved": {"booked", "rejected"},
    "booked": {"rejected"},
}


def verify_api_key(x_pp_key: str = Header(...)):
    if x_pp_key != PP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# --- Models ---


class HouseListing(BaseModel):
    id: str
    address: str | None = None
    city: str | None = None
    price: int | None = None
    sqm: int | None = None
    rooms: int | None = None
    year_built: int | None = None
    listing_url: str
    photos_url: str | None = None
    energy_label: str | None = None
    summary: str | None = None
    state: str = "new"
    source_email_id: str | None = None
    gf_sent: bool = False
    created_at: str
    updated_at: str
    decided_at: str | None = None


class HouseCreate(BaseModel):
    address: str | None = None
    city: str | None = None
    price: int | None = None
    sqm: int | None = None
    rooms: int | None = None
    year_built: int | None = None
    listing_url: str
    photos_url: str | None = None
    energy_label: str | None = None
    summary: str | None = None
    source_email_id: str | None = None
    gf_sent: bool = False


class HouseIngest(BaseModel):
    listing_url: str
    source_email_id: str | None = None
    gf_sent: bool = False


class HouseStateUpdate(BaseModel):
    state: str


# --- Storage ---


def _read_houses() -> list[dict]:
    if not HOUSES_FILE.exists():
        return []
    return json.loads(HOUSES_FILE.read_text())


def _write_houses(houses: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HOUSES_FILE.write_text(json.dumps(houses, indent=2))


def _find_house(houses: list[dict], house_id: str) -> dict | None:
    for h in houses:
        if h["id"] == house_id:
            return h
    return None


# --- Side effects ---


async def _send_whatsapp(message: str):
    """Send a message to the WhatsApp group via the WhatsApp tool."""
    if not WHATSAPP_GROUP_NAME:
        return
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{TOOLS_BASE}/whatsapp/send",
                json={"chat_name": WHATSAPP_GROUP_NAME, "message": message},
                headers={"X-PP-Key": PP_API_KEY},
            )
    except Exception:
        pass  # Best effort — don't fail the state change


def _format_house_summary(house: dict) -> str:
    """Format a house listing for WhatsApp."""
    parts = []
    if house.get("address"):
        parts.append(house["address"])
    if house.get("city"):
        parts.append(house["city"])
    if house.get("price"):
        parts.append(f"€{house['price']:,}".replace(",", "."))
    details = []
    if house.get("sqm"):
        details.append(f"{house['sqm']}m²")
    if house.get("rooms"):
        details.append(f"{house['rooms']} kamers")
    if house.get("energy_label"):
        details.append(f"Label {house['energy_label']}")
    if details:
        parts.append(" | ".join(details))
    if house.get("listing_url"):
        parts.append(house["listing_url"])
    return "\n".join(parts)


async def _on_state_change(house: dict, new_state: str):
    """Execute side effects when a house changes state."""
    if new_state == "sent_to_gf":
        summary = _format_house_summary(house)
        await _send_whatsapp(f"🏠 Nieuw huis:\n{summary}\n\nWat vind je?")
    elif new_state == "booked":
        addr = house.get("address", "een huis")
        await _send_whatsapp(f"📅 Bezichtiging aanvragen voor {addr}")


# --- Endpoints ---


@router.get("", response_model=list[HouseListing])
def list_houses(
    state: str | None = Query(None),
    _key: str = Depends(verify_api_key),
):
    houses = _read_houses()
    if state:
        houses = [h for h in houses if h.get("state") == state]
    houses.sort(key=lambda h: h.get("created_at", ""), reverse=True)
    return houses


@router.get("/pending", response_model=list[HouseListing])
def pending_houses(_key: str = Depends(verify_api_key)):
    houses = _read_houses()
    pending = [h for h in houses if h.get("state") == "new"]
    pending.sort(key=lambda h: h.get("created_at", ""), reverse=True)
    return pending


@router.post("", response_model=HouseListing, status_code=201)
def create_house(body: HouseCreate, _key: str = Depends(verify_api_key)):
    houses = _read_houses()

    # Check for duplicate listing URL
    for h in houses:
        if h.get("listing_url") == body.listing_url and h.get("state") != "rejected":
            raise HTTPException(status_code=409, detail="Listing already exists")

    now = datetime.now(timezone.utc).isoformat()
    house = {
        "id": uuid.uuid4().hex[:12],
        **body.model_dump(),
        "state": "new",
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
    }
    houses.append(house)
    _write_houses(houses)
    return house


@router.post("/ingest", response_model=HouseListing, status_code=201)
async def ingest_house(body: HouseIngest, _key: str = Depends(verify_api_key)):
    """Create a house listing by scraping a move.nl URL."""
    houses = _read_houses()

    # Check for duplicate
    for h in houses:
        if h.get("listing_url") == body.listing_url and h.get("state") != "rejected":
            raise HTTPException(status_code=409, detail="Listing already exists")

    try:
        scraped = await scrape_move_nl(body.listing_url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to scrape listing: {e}")

    now = datetime.now(timezone.utc).isoformat()
    house = {
        "id": uuid.uuid4().hex[:12],
        "address": scraped.get("address"),
        "city": scraped.get("city"),
        "price": scraped.get("price"),
        "sqm": scraped.get("sqm"),
        "rooms": scraped.get("rooms"),
        "year_built": scraped.get("year_built"),
        "listing_url": body.listing_url,
        "photos_url": scraped.get("photos_url"),
        "energy_label": scraped.get("energy_label"),
        "summary": scraped.get("summary"),
        "state": "new",
        "source_email_id": body.source_email_id,
        "gf_sent": body.gf_sent,
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
    }
    houses.append(house)
    _write_houses(houses)
    return house


@router.patch("/{house_id}", response_model=HouseListing)
async def update_house_state(
    house_id: str,
    body: HouseStateUpdate,
    _key: str = Depends(verify_api_key),
):
    if body.state not in VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state}")

    houses = _read_houses()
    house = _find_house(houses, house_id)
    if not house:
        raise HTTPException(status_code=404, detail="House not found")

    current = house["state"]
    allowed = STATE_TRANSITIONS.get(current, set())
    if body.state not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current}' to '{body.state}'"
        )

    now = datetime.now(timezone.utc).isoformat()
    house["state"] = body.state
    house["updated_at"] = now
    if body.state in ("rejected", "booked"):
        house["decided_at"] = now
    if body.state == "sent_to_gf":
        house["gf_sent"] = True

    _write_houses(houses)

    # Side effects (WhatsApp messages)
    await _on_state_change(house, body.state)

    return house


@router.delete("/{house_id}", status_code=204)
def delete_house(house_id: str, _key: str = Depends(verify_api_key)):
    houses = _read_houses()
    original_len = len(houses)
    houses = [h for h in houses if h["id"] != house_id]
    if len(houses) == original_len:
        raise HTTPException(status_code=404, detail="House not found")
    _write_houses(houses)


# --- Email trigger ---


@router.post("/check-email")
async def check_email(_key: str = Depends(verify_api_key)):
    """Check Gmail for new house listing emails and ingest them.

    Looks for emails from BUYING_AGENT_EMAIL containing move.nl links.
    """
    if not BUYING_AGENT_EMAIL:
        raise HTTPException(status_code=400, detail="BUYING_AGENT_EMAIL not configured")

    houses = _read_houses()
    known_email_ids = {h.get("source_email_id") for h in houses if h.get("source_email_id")}

    # Find the most recent house creation time to use as 'after'
    timestamps = [h["created_at"] for h in houses if h.get("source_email_id")]
    after = max(timestamps) if timestamps else None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {
                "q": f"from:{BUYING_AGENT_EMAIL}",
                "max_results": 10,
            }
            if after:
                params["after"] = after
            resp = await client.get(
                f"{TOOLS_BASE}/gmail/messages",
                params=params,
                headers={"X-PP-Key": PP_API_KEY},
            )
            resp.raise_for_status()
            messages = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail tool error: {e}")

    ingested = []
    for msg in messages:
        if msg["id"] in known_email_ids:
            continue

        # Get the email body to extract move.nl links
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                body_resp = await client.get(
                    f"{TOOLS_BASE}/gmail/messages/{msg['id']}/body",
                    headers={"X-PP-Key": PP_API_KEY},
                )
                body_resp.raise_for_status()
                body_data = body_resp.json()
        except Exception:
            continue

        # Find move.nl links
        move_links = [
            link for link in body_data.get("links", [])
            if "move.nl" in link
        ]
        # Also check the text for URLs
        text_links = re.findall(r'https?://[^\s]*move\.nl[^\s]*', body_data.get("text", ""))
        all_links = list(set(move_links + text_links))

        for link in all_links:
            try:
                scraped = await scrape_move_nl(link)
                now = datetime.now(timezone.utc).isoformat()
                house = {
                    "id": uuid.uuid4().hex[:12],
                    "address": scraped.get("address"),
                    "city": scraped.get("city"),
                    "price": scraped.get("price"),
                    "sqm": scraped.get("sqm"),
                    "rooms": scraped.get("rooms"),
                    "year_built": scraped.get("year_built"),
                    "listing_url": link,
                    "photos_url": scraped.get("photos_url"),
                    "energy_label": scraped.get("energy_label"),
                    "summary": scraped.get("summary"),
                    "state": "new",
                    "source_email_id": msg["id"],
                    "gf_sent": False,
                    "created_at": now,
                    "updated_at": now,
                    "decided_at": None,
                }
                # Check duplicate
                existing_urls = {h.get("listing_url") for h in houses if h.get("state") != "rejected"}
                if link not in existing_urls:
                    houses.append(house)
                    ingested.append(house)
            except Exception:
                continue

    if ingested:
        _write_houses(houses)

    return {"ingested": len(ingested), "houses": ingested}
