# PersonalSite

## Architecture
- **Backend**: FastAPI (Python, managed with `uv`)
- **Frontend**: Static HTML in `frontend/`
- **RipRaven**: Manga reader package in `ripraven/` (templates, downloader, pattern finder)
- **Data**: JSON file storage in `data/ripraven/`

RipRaven is the only thing the site serves; `/` returns 404.

## Key Routes
- `/api/ripraven/` — Manga reader API (auth: Google login, see below)
- `/api/auth/login|callback|logout` — Google sign-in for RipRaven
- `/api/health` — Health check

## RipRaven sign-in
`/ripraven*`, `/api/ripraven*` and `/rip_raven.html` require a Google login by `ALLOWED_EMAIL` (default `sappie.konig@gmail.com`); `backend/auth.py` does it as one HTTP middleware. Pages redirect to `/api/auth/login`, API calls get 401, and without OAuth config the gate returns 503 (fails closed). The session is an HS256 JWT cookie (`sheggle_session`, 90 days). OAuth client: GCP project `personal-agent-485520`, web client "sheggle.com login", redirect URI `https://sheggle.com/api/auth/callback`; the consent screen is in Testing mode, so the account must be a listed test user. `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `SESSION_SECRET` live in the root-only drop-in `/etc/systemd/system/sheggle.service.d/20-google-login.conf`; rotating `SESSION_SECRET` logs every browser out. The ravenscans userscript (`ripraven.user.js`) calls the API cross-site and only works while the browser holds a session cookie.

## Deployment (sheggle.com)
- **Server path**: `/srv/personalsite/`
- **Service**: `sheggle.service` (systemd, runs `uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000`)
- **Deploy flow**: `git push origin main` is enough — GitHub Actions SSHes in and runs `/usr/local/bin/update_sheggle` (fetch, `reset --hard origin/main`, `uv sync`, restart). Don't also pull/restart by hand; that restarts the service twice.
- **Nginx**: proxies `/ripraven` and `/api/` to port 8000

## Key Files
- `backend/app.py` — FastAPI app, route definitions
- `backend/auth.py` — Google sign-in gate
- `ripraven/web_reader.py` — RipRaven API

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
- **JSON data corruption**: State lives in `data/ripraven/*.json`. If a file is corrupt, service 500s on startup.

## RipRaven import flow
- **The site serves from `ravenscans.org`.** Series pages are `ravenscans.org/manga/<slug>/`, chapter pages `ravenscans.org/<slug>-chapter-<n>/`, images `cdnN.ravenscans.org`. `ravenscans.net` URLs still sitting in the caches 301 here, so they keep resolving as long as the client follows redirects. `parse_chapter_url` stores the canonical `/manga/<slug>/` form and `TrackingState` pins existing entries to it on load.
- **HTML pages sit behind Cloudflare's managed challenge**, including series pages, chapter pages, `/wp-json/`, and `/feed/`; plain httpx and curl_cffi both receive the Turnstile page. `ripraven/scraper.py` still uses `httpx.AsyncClient` for normal requests. On a Cloudflare 403/503 it calls `ripraven/cloudflare.py`: Patchright runs the installed Chrome headed under a temporary Xvfb display, waits for the challenge, and clicks its checkbox if one appears. The resulting `cf_clearance` cookie and matching browser user agent are copied into httpx, so subsequent HTML and direct `cdnN.ravenscans.org` image requests do not need a browser. A process-wide lock ensures concurrent series share one clearance attempt. Chrome and Xvfb stop as soon as the challenge is cleared; both are required system packages, but no Patchright/Playwright browser download is used.
- Where the two facts the scraper needs live:
  - **chapter numbers**: only on the series page, as `<li data-num="12.1">` next to the chapter link. The whole list is on one page, no pagination. Each `<li>` is parsed on its own and contributes the first chapter link inside it — **the link shape has changed twice** (`/chapter-<opaque-id>/` and `-chapter-<n>/`), so match on the word `chapter-` and never pin down the surrounding path.
  - **page images**: in the chapter page's `ts_reader.run({...})` JSON blob, already in reading order. Mixed extensions within one chapter (`0.webp`, `1.jpg`, …) are normal, and so is a chapter sliced into 150+ narrow strips.
- **Second source: `asurascans.com`.** Series pages are `asurascans.com/comics/<slug>-<8-hex hash>`, chapter pages `<series url>/chapter/<n>` (fractional as `81.5`), images `cdn.asurascans.com`. Same Cloudflare challenge, cleared the same way. The pages are Astro: the data is the HTML-escaped `props` attribute of an `<astro-island>`, JSON in which every value is wrapped as `[type, value]` — chapter list in the `ChapterListReact` island on the series page, page images in `ChapterReader` on the chapter page. **Each source needs its own `Referer`**: asura's CDN answers 403 to a request carrying ravenscans' Referer, so the scraper sets it per request, not on the client. **Page requests must send a browser-style `Accept`**: with httpx's default `*/*` asura rejects a valid `cf_clearance` cookie and every page would go through Chrome. The hash is dropped from the series name (`Damn_Reincarnation`) but kept in the stored `series_url`.
- `POST /api/ripraven/track` takes a chapter URL or the series page itself, from either source (`parse_source_url`). From a series page, Recently Read is seeded with the first chapter.
- **Novels are text chapters**: `downloads/<Series>/chapter_<n>/text.html` (an HTML fragment of `<h2>`, `<p>`, `<em>`, `<strong>`) plus the `completed` marker. The reader inserts the fragment as-is, so only write trusted, escaped HTML there. Such a series is not tracked; it is placed on disk by hand and indexed as described under `series_index.json` below. `Infinite_Mage_Novel` (1314 chapters, from an EPUB; the source has no chapter 1004) is the first; novel chapter 225 is where manhwa chapter 194 ends.
- Import runs server-side in a background worker (`ripraven/worker.py` + `ripraven/scraper.py`), started from the FastAPI lifespan. Per pass it walks every tracked series **3 at a time**, taking up to **8 missing chapters each** (oldest first) with a 0.2-0.6s jittered cooldown. Total load is bounded by a **process-wide semaphore of 12 concurrent image requests** on the scraper, not per chapter — that one constant is the knob for how hard the source gets hit. Sustained throughput is ~57 chapters/min.
- **Images get a 10s timeout, normal pages 30s.** Browser navigation also gets 30s, with up to 90s for Cloudflare's challenge to clear. Individual CDN nodes do go down and answer `522` only after ~20s; since a request holds a concurrency slot while it waits, a slow deadline on images stalls every series at once.
- **A failing series backs off exponentially** (1 min → 1 h, in `TrackingState`, in memory so a restart retries everything once) and its error is returned by `/api/ripraven/tracked` as `error`/`error_count` and shown in red on the home page. A series that is stuck must never look the same as one that is queued.
- **Chapter lists are re-scraped once older than 6h** (`CHAPTER_LIST_TTL_S`) — that refresh is what picks up new releases. Without it a series cached once would silently stop catching up.
- `POST /api/ripraven/track` registers a series from any chapter URL and **always** scrapes its chapter list synchronously first, so the series reports real counts the moment the import returns.
- A chapter is finished only when its `completed` marker is written, and already-downloaded images are skipped, so an interrupted chapter resumes instead of restarting.
- State: `data/ripraven/tracking.json` (tracked series), `chapter_cache.json` (chapter lists), `series_index.json`, `recent_chapters.json`, and `downloads/<Series>/chapter_<n>/{N.jpg, ..., completed}` (pages + completion marker).
- **Disk**: `/` is 38 GB and runs close to full. Series are moved to `/mnt/ripraven-cold/ripraven/downloads/<Series>` (SSHFS storagebox, 1 TB) and symlinked back into `downloads/`; new large series should be created there directly. The worker idles below 500 MB free rather than filling the disk.
- `series_index.json` is written wholesale from one process's in-memory state, so a second process writing it clobbers the first. To index chapters added out-of-band: `systemctl stop sheggle`, delete `series_index.json`, `systemctl start sheggle` — startup rebuilds it from disk.
- Chapter `0` (prologue) is downloaded but hidden from the home page's jump-to-chapter dropdown, which filters to numbers > 0.
