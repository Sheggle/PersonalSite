"""General-purpose Gmail tool — read-only Gmail API access via OAuth2."""

import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")
CREDENTIALS_DIR = Path(os.environ.get("GMAIL_CREDENTIALS_DIR", "/srv/personalsite/credentials"))
TOKEN_FILE = CREDENTIALS_DIR / "gmail-token.json"
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "personal-agent.json"

SCOPES = ["https://mail.google.com/"]

_service = None


def verify_api_key(x_pp_key: str = Header(...)):
    if x_pp_key != PP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _get_service():
    """Lazy-init Gmail API service with cached credentials."""
    global _service
    if _service is not None:
        return _service

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        else:
            raise HTTPException(
                status_code=503,
                detail="Gmail not authenticated. Run the OAuth flow on the server first.",
            )

    _service = build("gmail", "v1", credentials=creds)
    return _service


# --- HTML stripping ---


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.parts)
        # Collapse whitespace but keep newlines
        lines = [" ".join(line.split()) for line in text.split("\n")]
        return "\n".join(line for line in lines if line).strip()


def _strip_html(html: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


def _extract_links(html: str) -> list[str]:
    return re.findall(r'href=["\']([^"\']+)["\']', html)


# --- Helpers ---


def _decode_body(payload: dict) -> tuple[str | None, str | None]:
    """Extract plain text and HTML body from a message payload."""
    import base64

    plain = None
    html = None

    def _walk(part):
        nonlocal plain, html
        mime = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")
        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            if mime == "text/plain" and plain is None:
                plain = decoded
            elif mime == "text/html" and html is None:
                html = decoded
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    return plain, html


def _parse_headers(headers: list[dict]) -> dict[str, str]:
    """Extract common headers into a flat dict."""
    result = {}
    for h in headers:
        name = h.get("name", "").lower()
        if name in ("from", "to", "subject", "date", "message-id", "cc"):
            result[name] = h.get("value", "")
    return result


# --- Models ---


class MessageSummary(BaseModel):
    id: str
    thread_id: str
    subject: str | None = None
    sender: str | None = None
    date: str | None = None
    snippet: str | None = None


class MessageDetail(BaseModel):
    id: str
    thread_id: str
    headers: dict[str, str]
    snippet: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[dict] | None = None


class MessageBody(BaseModel):
    id: str
    text: str
    links: list[str]


# --- Endpoints ---


@router.get("/messages", response_model=list[MessageSummary])
def list_messages(
    q: str = Query("", description="Gmail search query"),
    max_results: int = Query(10, ge=1, le=50),
    after: str | None = Query(None, description="ISO timestamp — only messages after this"),
    _key: str = Depends(verify_api_key),
):
    service = _get_service()

    search_query = q
    if after:
        try:
            dt = datetime.fromisoformat(after)
            epoch = int(dt.timestamp())
            search_query = f"{search_query} after:{epoch}".strip()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'after' timestamp")

    try:
        result = service.users().messages().list(
            userId="me", q=search_query, maxResults=max_results
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {e}")

    messages = result.get("messages", [])
    if not messages:
        return []

    summaries = []
    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = _parse_headers(msg.get("payload", {}).get("headers", []))
            summaries.append(MessageSummary(
                id=msg["id"],
                thread_id=msg.get("threadId", ""),
                subject=headers.get("subject"),
                sender=headers.get("from"),
                date=headers.get("date"),
                snippet=msg.get("snippet"),
            ))
        except Exception:
            continue

    return summaries


@router.get("/messages/{message_id}", response_model=MessageDetail)
def get_message(message_id: str, _key: str = Depends(verify_api_key)):
    service = _get_service()
    try:
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {e}")

    payload = msg.get("payload", {})
    headers = _parse_headers(payload.get("headers", []))
    body_text, body_html = _decode_body(payload)

    attachments = []
    for part in payload.get("parts", []):
        if part.get("filename"):
            attachments.append({
                "filename": part["filename"],
                "mimeType": part.get("mimeType", ""),
                "size": part.get("body", {}).get("size", 0),
            })

    return MessageDetail(
        id=msg["id"],
        thread_id=msg.get("threadId", ""),
        headers=headers,
        snippet=msg.get("snippet"),
        body_text=body_text,
        body_html=body_html,
        attachments=attachments or None,
    )


@router.get("/messages/{message_id}/body", response_model=MessageBody)
def get_message_body(message_id: str, _key: str = Depends(verify_api_key)):
    service = _get_service()
    try:
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {e}")

    payload = msg.get("payload", {})
    body_text, body_html = _decode_body(payload)

    if body_html:
        text = _strip_html(body_html)
        links = _extract_links(body_html)
    elif body_text:
        text = body_text
        links = re.findall(r'https?://[^\s<>"]+', body_text)
    else:
        text = ""
        links = []

    return MessageBody(id=msg["id"], text=text, links=links)
