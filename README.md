# PersonalSite (sheggle.com)

Personal site and tools backend running at sheggle.com.

- `backend/app.py` — FastAPI app with all routes
- `frontend/` — Static HTML pages (`index.html`, `nightly.html`)
- `ripraven/` — Manga reader package mounted under `/api/ripraven`
- `backend/pp.py` — Personal Persistent todo API
- `backend/houses.py` — House decision state machine
- `backend/nightly.py` — Nightly agent proposal system
- `backend/tools/` — Agent tools (Gmail, WhatsApp)

## Local dev
```bash
uv sync
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
# http://127.0.0.1:8000/          — frontend
# http://127.0.0.1:8000/ripraven  — manga reader
# http://127.0.0.1:8000/nightly   — nightly proposal review UI
```

Set `PP_API_KEY` env var to authenticate API calls (default: `pp-dev-key-change-me`).

## API Overview

All authenticated endpoints require the `X-PP-Key` header.

| Route | Description |
|-------|-------------|
| `GET /api/health` | Health check |
| `/api/pp/todos` | Todo CRUD |
| `/api/pp/houses` | House listing state machine |
| `/api/tools/gmail/messages` | Gmail read-only |
| `/api/tools/whatsapp/send\|messages\|health` | WhatsApp via Shelly bot |
| `/api/nightly/proposals` | Nightly proposal CRUD |
| `/api/nightly/runs` | Nightly run summaries |
| `/api/ripraven/` | Manga reader API |

## Server layout (sheggle.com)

Repo lives at `/srv/personalsite/`. Service: `sheggle.service` (systemd, uvicorn on 127.0.0.1:8000).

Nginx serves `frontend/` as web root and reverse-proxies `/api/` and `/ripraven` to port 8000.

```nginx
server {
  listen 80;
  server_name sheggle.com www.sheggle.com;
  return 301 https://$host$request_uri;
}
server {
  listen 443 ssl http2;
  server_name sheggle.com www.sheggle.com;

  # certbot ssl_* lines here

  root /srv/personalsite/frontend;
  index index.html;

  location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location /ripraven {
    proxy_pass http://127.0.0.1:8000/ripraven;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```
