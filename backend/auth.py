"""Google sign-in gate for private parts of the site.

Every request under a PROTECTED_PREFIXES path needs a session cookie issued
after a Google login by ALLOWED_EMAIL. Pages redirect to the login, API calls
get 401. Without OAuth configuration the gate fails closed (503).
"""
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
ALLOWED_EMAIL = os.environ.get("ALLOWED_EMAIL", "sappie.konig@gmail.com").lower()
REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "https://sheggle.com/api/auth/callback")

PROTECTED_PREFIXES = ("/ripraven", "/api/ripraven", "/rip_raven.html")
SESSION_COOKIE = "sheggle_session"
STATE_COOKIE = "sheggle_oauth_state"
SESSION_DAYS = 90

router = APIRouter()


def _configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and SESSION_SECRET)


def session_email(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not SESSION_SECRET:
        return None
    try:
        claims = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    email = str(claims.get("email", "")).lower()
    return email if email == ALLOWED_EMAIL else None


def _is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p + "?") for p in PROTECTED_PREFIXES)


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not _is_protected(path):
        return await call_next(request)
    if not _configured():
        return JSONResponse({"detail": "Sign-in is not configured"}, status_code=503)
    if session_email(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    target = path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/api/auth/login?{urlencode({'next': target})}", status_code=302)


def _safe_next(next_url: str | None) -> str:
    # Only local paths, so the login can't be turned into an open redirect.
    if next_url and next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
        return next_url
    return "/ripraven"


@router.get("/login")
def login(next: str | None = None):
    if not _configured():
        raise HTTPException(503, "Sign-in is not configured")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "login_hint": ALLOWED_EMAIL,
        "prompt": "select_account",
    }
    resp = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=302)
    resp.set_cookie(STATE_COOKIE, f"{state}|{_safe_next(next)}", max_age=600,
                    httponly=True, secure=True, samesite="lax", path="/api/auth")
    return resp


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None):
    if not _configured():
        raise HTTPException(503, "Sign-in is not configured")
    expected_state, _, next_url = (request.cookies.get(STATE_COOKIE) or "").partition("|")
    if not code or not state or not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(400, "Login expired or invalid, try again")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    if r.status_code != 200:
        raise HTTPException(400, "Google rejected the login")

    # The id_token comes straight from Google's token endpoint over TLS, so its
    # signature needs no separate check (OpenID Connect Core 3.1.3.7).
    claims = jwt.decode(r.json()["id_token"], options={"verify_signature": False})
    email = str(claims.get("email", "")).lower()
    if (claims.get("aud") != CLIENT_ID
            or claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com")
            or not claims.get("email_verified")
            or email != ALLOWED_EMAIL):
        raise HTTPException(403, "This account has no access")

    session = jwt.encode({"email": email, "exp": int(time.time()) + SESSION_DAYS * 86400},
                         SESSION_SECRET, algorithm="HS256")
    resp = RedirectResponse(_safe_next(next_url), status_code=302)
    resp.set_cookie(SESSION_COOKIE, session, max_age=SESSION_DAYS * 86400,
                    httponly=True, secure=True, samesite="lax", path="/")
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
