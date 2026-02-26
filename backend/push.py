"""APNs silent push notifications via HTTP/2 + JWT."""

import json
import os
import time
from pathlib import Path

import httpx
import jwt

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEVICES_FILE = DATA_DIR / "pp_devices.json"

APNS_KEY_PATH = os.environ.get("APNS_KEY_PATH", "/srv/personalsite/credentials/apns-key.p8")
APNS_KEY_ID = os.environ.get("APNS_KEY_ID", "")
APNS_TEAM_ID = os.environ.get("APNS_TEAM_ID", "")
APNS_TOPIC = "com.sheggle.PeronsalPersistent"
APNS_USE_SANDBOX = os.environ.get("APNS_SANDBOX", "1") == "1"

APNS_HOST = "https://api.sandbox.push.apple.com" if APNS_USE_SANDBOX else "https://api.push.apple.com"


def _read_devices() -> list[str]:
    if not DEVICES_FILE.exists():
        return []
    return json.loads(DEVICES_FILE.read_text())


def _write_devices(tokens: list[str]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEVICES_FILE.write_text(json.dumps(tokens))


def register_device(token: str):
    tokens = _read_devices()
    if token not in tokens:
        tokens.append(token)
        _write_devices(tokens)


def remove_device(token: str):
    tokens = _read_devices()
    tokens = [t for t in tokens if t != token]
    _write_devices(tokens)


def _make_jwt() -> str:
    key_path = Path(APNS_KEY_PATH)
    if not key_path.exists() or not APNS_KEY_ID or not APNS_TEAM_ID:
        return ""
    key = key_path.read_text()
    now = int(time.time())
    payload = {"iss": APNS_TEAM_ID, "iat": now}
    return jwt.encode(payload, key, algorithm="ES256", headers={"kid": APNS_KEY_ID})


async def send_silent_push():
    """Send a silent push to all registered devices."""
    token_str = _make_jwt()
    if not token_str:
        return

    devices = _read_devices()
    if not devices:
        return

    async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
        for device_token in devices:
            try:
                await client.post(
                    f"{APNS_HOST}/3/device/{device_token}",
                    headers={
                        "authorization": f"bearer {token_str}",
                        "apns-topic": APNS_TOPIC,
                        "apns-push-type": "background",
                        "apns-priority": "5",
                    },
                    json={"aps": {"content-available": 1}, "type": "house-update"},
                )
            except Exception:
                pass
