# PersonalSite

## Architecture
- **Backend**: FastAPI (Python, managed with `uv`)
- **Frontend**: Static HTML in `frontend/`
- **RipRaven**: Manga reader package in `ripraven/` (templates, downloader, pattern finder)
- **PP (Peronsal Persistent)**: Todo + House decision API in `backend/pp.py` and `backend/houses.py`
- **Tools**: General-purpose agent tools in `backend/tools/` (Gmail, WhatsApp)
- **Data**: JSON file storage in `data/` (`pp_todos.json`, `pp_houses.json`, `ripraven/`)

## Key Routes
- `/api/pp/todos` — Todo CRUD (auth: `X-PP-Key` header)
- `/api/pp/houses` — House listing state machine (auth: `X-PP-Key`)
- `/api/tools/gmail/messages` — Gmail read-only API (auth: `X-PP-Key`)
- `/api/tools/whatsapp/send|messages|health` — WhatsApp proxy to Shelly bot (auth: `X-PP-Key`)
- `/api/ripraven/` — Manga reader API
- `/api/health` — Health check

## House Decision Flow
States: `new → sent_to_gf → approved → booked` (reject from any)
- State changes trigger WhatsApp messages to the group
- Email trigger: `POST /api/pp/houses/check-email` checks Gmail for buying agent emails
- Monitor: `backend/house_monitor.py` polls WhatsApp group for GF links/approvals

## External Dependencies
- **Shelly bot** (37.27.191.4:8100): WhatsApp Web bridge via Playwright
- **Gmail API**: OAuth2 credentials at `/srv/personalsite/credentials/`
- **iOS app**: PeronsalPersistent (separate Xcode project)

## Deployment (sheggle.com)
- **Server path**: `/srv/personalsite/`
- **Service**: `sheggle.service` (systemd, runs `uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000`)
- **Deploy flow**: `git push origin main` → `ssh deploy@sheggle.com "cd /srv/personalsite && git pull origin main"` → `sudo systemctl restart sheggle.service`
- **Nginx**: proxies `/ripraven` and `/api/` to port 8000

## Key Files
- `backend/app.py` — FastAPI app, route definitions
- `backend/pp.py` — Todo API with JSON storage
- `backend/houses.py` — House decision state machine
- `backend/house_scraper.py` — move.nl listing scraper
- `backend/house_monitor.py` — WhatsApp group polling loop
- `backend/tools/gmail.py` — Gmail API tool
- `backend/tools/whatsapp.py` — WhatsApp proxy tool
- `scripts/gmail_oauth_setup.py` — One-time Gmail OAuth setup
- `ripraven/web_reader.py` — RipRaven API
