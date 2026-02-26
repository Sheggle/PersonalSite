"""WhatsApp group monitor — polls for GF house links and approvals.

Run as: python -m backend.house_monitor
Or via systemd timer calling the /api/pp/houses/poll endpoint.
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")
BASE_URL = os.environ.get("PP_BASE_URL", "http://127.0.0.1:8000")
WHATSAPP_GROUP_NAME = os.environ.get("WHATSAPP_GROUP_NAME", "")
GF_NAME = os.environ.get("GF_WHATSAPP_NAME", "")  # Her name as it appears in WhatsApp
POLL_INTERVAL = int(os.environ.get("HOUSE_POLL_INTERVAL", "120"))  # seconds

APPROVAL_PATTERNS = re.compile(
    r"^(ok|ja|leuk|top|goed|mooi|nice|yes|prima|doen|bezichtigen)\b",
    re.IGNORECASE,
)

HEADERS = {"X-PP-Key": PP_API_KEY, "Content-Type": "application/json"}


async def _api_get(client: httpx.AsyncClient, path: str, params: dict | None = None):
    resp = await client.get(f"{BASE_URL}{path}", params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


async def _api_post(client: httpx.AsyncClient, path: str, body: dict):
    resp = await client.post(f"{BASE_URL}{path}", json=body, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


async def _api_patch(client: httpx.AsyncClient, path: str, body: dict):
    resp = await client.patch(f"{BASE_URL}{path}", json=body, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


async def poll_once(client: httpx.AsyncClient):
    """Run one poll cycle: check WhatsApp messages for house-related activity."""
    if not WHATSAPP_GROUP_NAME:
        return

    # Get recent WhatsApp messages
    try:
        messages = await _api_get(
            client,
            "/api/tools/whatsapp/messages",
            params={"chat_name": WHATSAPP_GROUP_NAME, "limit": 30},
        )
    except Exception as e:
        print(f"[monitor] WhatsApp fetch error: {e}")
        return

    if not messages:
        return

    # Get current houses
    try:
        houses = await _api_get(client, "/api/pp/houses")
    except Exception as e:
        print(f"[monitor] Houses fetch error: {e}")
        return

    houses_by_state = {}
    for h in houses:
        houses_by_state.setdefault(h["state"], []).append(h)

    # Check for GF sending move.nl links → create house with gf_sent=True
    existing_urls = {h.get("listing_url") for h in houses if h.get("state") != "rejected"}

    for msg in messages:
        sender = msg.get("sender", "")
        text = msg.get("text", "")

        # Only process GF messages (if GF_NAME is set)
        is_gf = GF_NAME and GF_NAME.lower() in sender.lower()

        if is_gf:
            # Check for move.nl links
            move_links = re.findall(r'https?://[^\s]*move\.nl[^\s]*', text)
            for link in move_links:
                if link not in existing_urls:
                    try:
                        result = await _api_post(
                            client,
                            "/api/pp/houses/ingest",
                            {"listing_url": link, "gf_sent": True},
                        )
                        existing_urls.add(link)
                        print(f"[monitor] Ingested GF house: {link}")
                    except Exception as e:
                        print(f"[monitor] Ingest error for {link}: {e}")

            # Check for approval messages when there's a house in sent_to_gf state
            sent_houses = houses_by_state.get("sent_to_gf", [])
            if sent_houses and APPROVAL_PATTERNS.match(text.strip()):
                # Approve the most recently sent house
                latest = max(sent_houses, key=lambda h: h.get("updated_at", ""))
                try:
                    await _api_patch(
                        client,
                        f"/api/pp/houses/{latest['id']}",
                        {"state": "approved"},
                    )
                    print(f"[monitor] Approved house: {latest.get('address', latest['id'])}")
                except Exception as e:
                    print(f"[monitor] Approval error: {e}")


async def run_loop():
    """Run the monitor in a loop."""
    print(f"[monitor] Starting house monitor (interval={POLL_INTERVAL}s)")
    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            try:
                await poll_once(client)
            except Exception as e:
                print(f"[monitor] Poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_loop())
