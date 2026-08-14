# PersonalSite

## Architecture
- **Backend**: FastAPI (Python, managed with `uv`)
- **Frontend**: Static HTML in `frontend/`
- **RipRaven**: Manga reader package in `ripraven/` (templates, downloader, pattern finder)
- **PP (Personal Persistent)**: Todo + House decision API in `backend/pp.py` and `backend/houses.py`
- **Tools**: General-purpose agent tools in `backend/tools/` (Gmail, WhatsApp)
- **Nightly Agent**: Proposal review system in `backend/nightly.py` + `frontend/nightly.html`
- **Data**: JSON file storage in `data/` (`pp_todos.json`, `pp_houses.json`, `nightly_proposals.json`, `ripraven/`)

## Key Routes
- `/api/pp/todos` — Todo CRUD (auth: `X-PP-Key` header)
- `/api/pp/houses` — House listing state machine (auth: `X-PP-Key`)
- `/api/tools/gmail/messages` — Gmail read-only API (auth: `X-PP-Key`)
- `/api/tools/whatsapp/send|messages|health` — WhatsApp proxy to Shelly bot (auth: `X-PP-Key`)
- `/api/nightly/proposals` — Nightly agent proposal CRUD (auth: `X-PP-Key`)
- `/api/nightly/runs` — Nightly run summaries (auth: `X-PP-Key`)
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
- `backend/nightly.py` — Nightly agent proposal API with JSON storage
- `frontend/nightly.html` — Nightly proposal review UI
- `ripraven/web_reader.py` — RipRaven API

## Environment Variables

Set in `/etc/systemd/system/sheggle.service` on sheggle.com:

| Variable | Purpose |
|----------|---------|
| `PP_API_KEY` | Auth key for all `/api/pp/` and `/api/nightly/` endpoints |
| `GMAPS_API_KEY` | Google Maps API (travel time in house listings) |
| `APNS_KEY_ID` | APNs push notification key ID (XNY5F5NFLC) |
| `APNS_TEAM_ID` | Apple Developer Team ID (3V7YQY3S3D) |
| `APNS_KEY_PATH` | Path to `.p8` APNs key file (`/srv/personalsite/credentials/apns-key.p8`) |
| `APNS_SANDBOX` | `true` for debug/dev iOS builds, `false` for TestFlight/App Store |

## Health Check
```bash
curl https://sheggle.com/api/health
ssh deploy@sheggle.com 'systemctl status sheggle.service'
```

## Logs
```bash
ssh deploy@sheggle.com 'journalctl -u sheggle.service -f'        # live
ssh deploy@sheggle.com 'journalctl -u sheggle.service -n 200'    # last 200 lines
```

## Rollback
```bash
ssh deploy@sheggle.com
cd /srv/personalsite
git log --oneline -10
git checkout <commit-hash>
sudo systemctl restart sheggle.service
curl localhost:8000/api/health
```

## Common Pitfalls
- **Shelly bot down**: WhatsApp endpoints (`/api/tools/whatsapp/`) fail if 37.27.191.4:8100 is unreachable. Check: `ssh agent@37.27.191.4 'curl -s localhost:8100/health'`. If down, restart the Shelly service on the agent box.
- **Gmail OAuth expired**: If Gmail calls return 401, re-run `uv run python scripts/gmail_oauth_setup.py` on sheggle.com. Credentials at `/srv/personalsite/credentials/`.
- **JSON data corruption**: State lives in `data/*.json`. If a file is corrupt, service 500s on startup. Fix: `git show HEAD:data/<file>.json > data/<file>.json`, then restart.
- **APNs sandbox mismatch**: Debug iOS builds need `APNS_SANDBOX=true`. TestFlight/App Store needs `APNS_SANDBOX=false`. Wrong value = silent push failures, no error in logs.

## RipRaven import flow
- **ravenscans moved from `ravenscans.org` to `ravenscans.net`.** Chapter URLs are now `/series/<slug>/chapter-<post-id>/`, where the id is *not* the chapter number. Old .org URLs 301 to their .net equivalents, so the pre-move URLs still sitting in `chapter_cache.json` keep resolving as long as the client follows redirects. Images still come from `cdnN.ravenscans.org`.
- **No Cloudflare challenge any more**: plain httpx reaches both pages and images from the VPS. `ripraven/scraper.py` is an `httpx.AsyncClient` — no patchright, no xvfb, no Turnstile clicking, no profile rotation. If a challenge ever comes back, `ripraven/static/ripraven.user.js` plus the `/queue` endpoints are the browser-side fallback (nothing uses them while the server can fetch directly).
- Where the two facts the scraper needs live:
  - **chapter numbers**: only on the series page, as `<li data-num="12.1">` next to the chapter link. The whole list is on one page, no pagination.
  - **page images**: in the chapter page's `ts_reader.run({...})` JSON blob, already in reading order. Mixed extensions within one chapter (`0.webp`, `1.jpg`, …) are normal.
- Import runs server-side in a background worker (`ripraven/worker.py` + `ripraven/scraper.py`), started from the FastAPI lifespan. Per pass it downloads one missing chapter per tracked series (round-robin, oldest chapter first) with 4 concurrent image fetches and a 2-5s jittered cooldown between chapters. A series that fails is logged and skipped so it cannot stall the rest.
- **Chapter lists are re-scraped once older than 6h** (`CHAPTER_LIST_TTL_S`) — that refresh is what picks up new releases. Without it a series cached once would silently stop catching up.
- `POST /api/ripraven/track` registers a series from any chapter URL and caches its chapter list straight away, so the worker starts downloading on its next pass.
- State: `data/ripraven/tracking.json` (tracked series), `chapter_cache.json` (chapter lists), `series_index.json`, `recent_chapters.json`, and `downloads/<Series>/chapter_<n>/{N.jpg, ..., completed}` (pages + completion marker).
- **Disk**: `/` is 38 GB and runs close to full. Series are moved to `/mnt/ripraven-cold/ripraven/downloads/<Series>` (SSHFS storagebox, 1 TB) and symlinked back into `downloads/`; new large series should be created there directly. The worker idles below 500 MB free rather than filling the disk.
- `series_index.json` is written wholesale from one process's in-memory state, so a second process writing it clobbers the first. To index chapters added out-of-band: `systemctl stop sheggle`, delete `series_index.json`, `systemctl start sheggle` — startup rebuilds it from disk.
- Observability gotcha: the ripraven logger has no handler, so worker log lines (🦅/📥) reach neither journald nor `logs/ripraven.log` (stale since Oct 2025). Watch progress via mtimes in the downloads dir.

## Nightly Agent Integration
This service is the submission target for the nightly documentation agent:
- Agent posts proposals to `POST /api/nightly/proposals/batch` with `X-PP-Key` header
- Proposals stored in `data/nightly_proposals.json`
- Review UI at `https://sheggle.com/nightly.html`
- Accept/reject a proposal: `PATCH /api/nightly/proposals/{id}` with body `{"status": "accepted"}`
- Bulk decide a run: `PATCH /api/nightly/runs/{run_id}`
