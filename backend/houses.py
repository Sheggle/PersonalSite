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

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HOUSES_FILE = DATA_DIR / "pp_houses.json"

PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")
GMAPS_KEY = os.environ.get("GMAPS_API_KEY", "")

TOOLS_BASE = "http://127.0.0.1:8000/api/tools"
WHATSAPP_GROUP_NAME = os.environ.get("WHATSAPP_GROUP_NAME", "")

VALID_STATES = {"new", "sent_to_gf", "approved", "booked", "rejected"}
STATE_TRANSITIONS = {
    "new": {"sent_to_gf", "booked", "rejected"},
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
    address: str
    price: int | None = None
    sqm: int | None = None
    rooms: int | None = None
    travel_min: int | None = None
    listing_url: str
    state: str = "new"
    gf_sent: bool = False
    created_at: str
    decided_at: str | None = None


class HouseCreate(BaseModel):
    address: str
    price: int | None = None
    sqm: int | None = None
    rooms: int | None = None
    listing_url: str
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


# --- Email parsing ---


def _parse_overduyn_email(text: str, links: list[str]) -> list[dict]:
    """Parse Overduyn 'nieuwe objecten' email into house dicts.

    Pattern per house:
        Match: XX%
        Address Postcode City
        Vraagprijs: € XXX.XXX,- kosten koper
        Type | XX m² / XX m² | X kamers (X slaapkamers)
    """
    # Get unique exchange-object links (one per house, in order)
    seen = set()
    move_links = []
    for link in links:
        if "exchange-object" in link:
            # Normalize: strip searchObjectId param which varies
            base = link.split("/overzicht")[0] if "/overzicht" in link else link
            if base not in seen:
                seen.add(base)
                move_links.append(link)

    # Split on "Match: XX%" to find house blocks
    blocks = re.split(r"Match:\s*\d+%", text)
    blocks = [b.strip() for b in blocks[1:] if b.strip()]  # skip preamble

    houses = []
    for i, block in enumerate(blocks):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        house: dict = {}

        # First line: address (e.g. "Bessemerlaan 48 3553 GE Utrecht")
        house["address"] = lines[0]

        # Price line
        for line in lines:
            price_match = re.search(r"€\s*([\d.]+)", line)
            if price_match:
                house["price"] = int(price_match.group(1).replace(".", ""))
                break

        # Details line (sqm, rooms)
        for line in lines:
            sqm_match = re.search(r"(\d+)\s*m²", line)
            if sqm_match:
                house["sqm"] = int(sqm_match.group(1))
            rooms_match = re.search(r"(\d+)\s*kamers?", line)
            if rooms_match:
                house["rooms"] = int(rooms_match.group(1))

        # Link
        house["listing_url"] = move_links[i] if i < len(move_links) else ""

        if house.get("address") and house.get("listing_url"):
            houses.append(house)

    return houses


# --- Travel time ---


async def _get_travel_time(address: str) -> int | None:
    """Get transit travel time in minutes from address to Utrecht Centraal.

    Uses Google Maps Directions API, departing Monday 8:00 CET.
    Returns actual moving time (excludes initial wait).
    """
    if not GMAPS_KEY:
        return None

    # Next Monday at 8:00 CET
    from datetime import timedelta
    import calendar

    now = datetime.now(timezone.utc)
    cet = timezone(timedelta(hours=1))
    today_cet = now.astimezone(cet).date()
    days_until_monday = (7 - today_cet.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today_cet + timedelta(days=days_until_monday)
    departure = datetime(next_monday.year, next_monday.month, next_monday.day, 8, 0, tzinfo=cet)
    dep_ts = int(departure.timestamp())

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": address,
                    "destination": "Utrecht Centraal",
                    "mode": "transit",
                    "departure_time": dep_ts,
                    "key": GMAPS_KEY,
                },
            )
            data = resp.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return None

        leg = data["routes"][0]["legs"][0]
        # departure_time and arrival_time give us actual moving time
        # (excludes the "wait until 8:10 to leave" part)
        dep = leg.get("departure_time", {}).get("value")
        arr = leg.get("arrival_time", {}).get("value")
        if dep and arr:
            return (arr - dep) // 60

        # Fallback to duration field
        return leg.get("duration", {}).get("value", 0) // 60
    except Exception:
        return None


# --- Side effects ---


async def _send_whatsapp(message: str):
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
        pass


def _format_house(house: dict) -> str:
    parts = [house.get("address", "?")]
    if house.get("price"):
        parts.append(f"€{house['price']:,}".replace(",", "."))
    details = []
    if house.get("sqm"):
        details.append(f"{house['sqm']}m²")
    if house.get("rooms"):
        details.append(f"{house['rooms']} kamers")
    if details:
        parts.append(" | ".join(details))
    if house.get("listing_url"):
        parts.append(house["listing_url"])
    return "\n".join(parts)


async def _on_state_change(house: dict, new_state: str):
    if new_state == "sent_to_gf":
        await _send_whatsapp(f"🏠 Nieuw huis:\n{_format_house(house)}\n\nWat vind je?")
    elif new_state == "booked":
        await _send_whatsapp(f"📅 Bezichtiging aanvragen voor {house.get('address', '?')}")


# --- Endpoints ---


@router.get("", response_model=list[HouseListing])
def list_houses(state: str | None = Query(None), _key: str = Depends(verify_api_key)):
    houses = _read_houses()
    if state:
        houses = [h for h in houses if h.get("state") == state]
    houses.sort(key=lambda h: h.get("created_at", ""), reverse=True)
    return houses


@router.get("/pending", response_model=list[HouseListing])
def pending_houses(_key: str = Depends(verify_api_key)):
    houses = _read_houses()
    return [h for h in houses if h.get("state") == "new"]


@router.post("", response_model=HouseListing, status_code=201)
def create_house(body: HouseCreate, _key: str = Depends(verify_api_key)):
    houses = _read_houses()
    now = datetime.now(timezone.utc).isoformat()
    house = {
        "id": uuid.uuid4().hex[:12],
        **body.model_dump(),
        "state": "new",
        "created_at": now,
        "decided_at": None,
    }
    houses.append(house)
    _write_houses(houses)
    return house


async def _make_house(p: dict, gf_sent: bool = False) -> dict:
    """Build a house dict from parsed data, enriching with travel time."""
    now = datetime.now(timezone.utc).isoformat()
    travel = await _get_travel_time(p["address"])
    return {
        "id": uuid.uuid4().hex[:12],
        "address": p["address"],
        "price": p.get("price"),
        "sqm": p.get("sqm"),
        "rooms": p.get("rooms"),
        "travel_min": travel,
        "listing_url": p["listing_url"],
        "state": "new",
        "gf_sent": gf_sent,
        "created_at": now,
        "decided_at": None,
    }


@router.post("/ingest-email", status_code=201)
async def ingest_email(
    email_id: str = Query(...),
    _key: str = Depends(verify_api_key),
):
    """Parse an Overduyn email and create house listings from it."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{TOOLS_BASE}/gmail/messages/{email_id}/body",
                headers={"X-PP-Key": PP_API_KEY},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail error: {e}")

    parsed = _parse_overduyn_email(body.get("text", ""), body.get("links", []))
    if not parsed:
        raise HTTPException(status_code=422, detail="No houses found in email")

    houses = _read_houses()
    existing_urls = {h.get("listing_url") for h in houses if h.get("state") != "rejected"}

    created = []
    for p in parsed:
        if p["listing_url"] in existing_urls:
            continue
        house = await _make_house(p)
        houses.append(house)
        existing_urls.add(p["listing_url"])
        created.append(house)

    if created:
        _write_houses(houses)

    return {"ingested": len(created), "houses": created}


@router.patch("/{house_id}", response_model=HouseListing)
async def update_house_state(house_id: str, body: HouseStateUpdate, _key: str = Depends(verify_api_key)):
    if body.state not in VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state}")

    houses = _read_houses()
    house = next((h for h in houses if h["id"] == house_id), None)
    if not house:
        raise HTTPException(status_code=404, detail="House not found")

    current = house["state"]
    if body.state not in STATE_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=400, detail=f"Cannot go from '{current}' to '{body.state}'")

    house["state"] = body.state
    if body.state in ("rejected", "booked"):
        house["decided_at"] = datetime.now(timezone.utc).isoformat()
    if body.state == "sent_to_gf":
        house["gf_sent"] = True

    _write_houses(houses)
    await _on_state_change(house, body.state)
    return house


@router.delete("/{house_id}", status_code=204)
def delete_house(house_id: str, _key: str = Depends(verify_api_key)):
    houses = _read_houses()
    new = [h for h in houses if h["id"] != house_id]
    if len(new) == len(houses):
        raise HTTPException(status_code=404, detail="House not found")
    _write_houses(new)


@router.post("/enrich-travel")
async def enrich_travel(_key: str = Depends(verify_api_key)):
    """Backfill travel_min for houses that don't have it yet."""
    houses = _read_houses()
    updated = 0
    for house in houses:
        if house.get("travel_min") is not None:
            continue
        if house.get("state") == "rejected":
            continue
        travel = await _get_travel_time(house["address"])
        if travel is not None:
            house["travel_min"] = travel
            updated += 1
    if updated:
        _write_houses(houses)
    return {"updated": updated}


# --- Email check ---


@router.post("/check-email")
async def check_email(_key: str = Depends(verify_api_key)):
    """Scan recent Overduyn emails and ingest any new houses."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{TOOLS_BASE}/gmail/messages",
                params={"q": "from:info@overduyn.nl subject:nieuwe objecten", "max_results": 10},
                headers={"X-PP-Key": PP_API_KEY},
            )
            resp.raise_for_status()
            messages = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail error: {e}")

    total = 0
    all_houses = []
    for msg in messages:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                body_resp = await client.get(
                    f"{TOOLS_BASE}/gmail/messages/{msg['id']}/body",
                    headers={"X-PP-Key": PP_API_KEY},
                )
                body_resp.raise_for_status()
                body = body_resp.json()
        except Exception:
            continue

        parsed = _parse_overduyn_email(body.get("text", ""), body.get("links", []))
        houses = _read_houses()
        existing_urls = {h.get("listing_url") for h in houses}

        for p in parsed:
            if p["listing_url"] in existing_urls:
                continue
            house = await _make_house(p)
            houses.append(house)
            existing_urls.add(p["listing_url"])
            all_houses.append(house)
            total += 1

        if all_houses:
            _write_houses(houses)

    return {"ingested": total, "houses": all_houses}
