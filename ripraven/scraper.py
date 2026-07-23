"""Cloudflare-bypass scraper for ripraven.

Cloudflare's managed challenge blocks every plain HTTP client (curl_cffi,
httpx with browser TLS impersonation, headless playwright). The only thing
that gets through is a real Chrome under xvfb with a one-time Turnstile click.
We keep one persistent context alive; cf_clearance carries across calls. On a
403 we click Turnstile again and retry.
"""

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional

from patchright.async_api import async_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

CHAPTER_HREF_RE = re.compile(r'href="(https?://ravenscans\.org/[^"]*?-chapter-(\d+(?:-\d+)?)[^"]*?)"')
IMAGE_URL_RE = re.compile(r'https://cdn\d+\.ravenscans\.org/[^"\s\'>)]+\.(?:jpg|jpeg|png|webp)', re.IGNORECASE)
RAVENSCANS_HOME = 'https://ravenscans.org/'
# Cloudflare sometimes tarpits an individual image fetch: 200 OK headers
# arrive but the body never finishes. A healthy image (~300 KB) completes in
# well under a second, so time out fast and retry instead of burning the
# default 30s on a dead transfer.
IMAGE_FETCH_TIMEOUT_MS = 15_000
IMAGE_FETCH_ATTEMPTS = 3
# Concurrent image fetches within a chapter. Modest on purpose: running
# flat-out at ~300 images/min triggers Cloudflare's adaptive rate-limit after
# ~100 chapters and the profile gets sticky-blocked.
IMAGE_CONCURRENCY = 3


def _natural_sort_key(text: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', text)]


class CFScraper:
    def __init__(self, profile_dir: str | Path = "/tmp/ripraven-profile"):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        # Serializes _solve calls from concurrent image fetches — the shared
        # page can only navigate one URL at a time.
        self._solve_lock = asyncio.Lock()

    async def start(self):
        if self._ctx is not None:
            return
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel='chrome',
            headless=False,
            no_viewport=True,
        )
        self._page = await self._ctx.new_page()
        logger.info("🦅 cf-scraper: browser context started")

    async def close(self):
        try:
            if self._ctx:
                await self._ctx.close()
        finally:
            self._ctx = None
            self._page = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    async def reset(self):
        """Close browser and wipe the persistent profile.

        After ~100 successful chapters Cloudflare started 403-ing every image
        on this profile, even after Turnstile re-clicks — a 'sticky' bot cookie
        in the jar. Wiping the profile forces a clean re-solve from scratch
        and recovers reliably.
        """
        await self.close()
        try:
            if self.profile_dir.exists():
                shutil.rmtree(self.profile_dir)
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                logger.info("🦅 cf-scraper: wiped profile dir %s", self.profile_dir)
        except Exception:
            logger.exception("could not wipe profile dir")

    async def _ensure_started(self):
        if self._ctx is None:
            await self.start()

    async def _solve(self, url: str) -> bool:
        """Navigate to URL and clear any Cloudflare challenge.

        Returns True only if we end up on a real ravenscans page — verified
        both by title (no longer 'Just a moment...') AND by content (HTML
        contains either a cdn ravenscans image URL or 'ravenscans.org' link).
        Without the content check we'd report success when CF served us its
        'Sorry, you have been blocked' page (different title, no content).
        """
        assert self._page
        try:
            await self._page.goto(url, timeout=30_000, wait_until='domcontentloaded')
        except Exception as e:
            logger.warning("goto failed: %s", e)
        for i in range(20):
            await self._page.wait_for_timeout(800)
            try:
                title = await self._page.title()
            except Exception:
                title = ''
            if 'Just a moment' not in title and title.strip():
                # Sanity-check: was this actually a chapter / series page?
                try:
                    html = await self._page.content()
                except Exception:
                    html = ''
                if IMAGE_URL_RE.search(html) or 'ravenscans-content' in html or 'wp-content' in html:
                    return True
                logger.warning("🦅 cf-scraper: title cleared (%r) but content looks blocked at %s", title, url)
                return False
            try:
                await self._page.mouse.move(100 + i * 5, 200 + i * 3)
            except Exception:
                pass
            if i == 4:
                try:
                    fr = self._page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
                    await fr.locator('input[type=checkbox]').click(timeout=3000)
                    logger.info("🦅 cf-scraper: clicked Turnstile at %s", url)
                except Exception:
                    pass
        logger.warning("🦅 cf-scraper: could not solve challenge at %s", url)
        return False

    async def scrape_chapter_list(self, series_url: str) -> List[dict]:
        await self._ensure_started()
        async with self._lock:
            ok = await self._solve(series_url)
            if not ok:
                raise RuntimeError(f"CF challenge not solved at {series_url}")
            html = await self._page.content()
        seen, chapters = set(), []
        for m in CHAPTER_HREF_RE.finditer(html):
            num = m.group(2).replace('-', '.')
            if num in seen:
                continue
            seen.add(num)
            chapters.append({'number': num, 'url': m.group(1)})
        if not chapters:
            raise RuntimeError(f"no chapters parsed from {series_url}")
        return chapters

    async def _fetch_image(self, url: str, chapter_url: str) -> bytes:
        """Fetch one image with retries.

        Cloudflare intermittently stalls a transfer (headers arrive, body
        never completes). Retrying the same URL almost always succeeds, so a
        stall costs one short timeout instead of failing the whole chapter.
        """
        last_err: Optional[Exception] = None
        for attempt in range(1, IMAGE_FETCH_ATTEMPTS + 1):
            try:
                r = await self._ctx.request.get(
                    url, headers={'Referer': RAVENSCANS_HOME},
                    timeout=IMAGE_FETCH_TIMEOUT_MS,
                )
                if r.status == 403:
                    async with self._solve_lock:
                        await self._solve(chapter_url)
                    r = await self._ctx.request.get(
                        url, headers={'Referer': RAVENSCANS_HOME},
                        timeout=IMAGE_FETCH_TIMEOUT_MS,
                    )
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status} fetching {url}")
                body = await r.body()
                if not body:
                    raise RuntimeError(f"empty body for {url}")
                return body
            except Exception as e:
                last_err = e
                logger.warning("🦅 image fetch %d/%d failed for %s: %s",
                               attempt, IMAGE_FETCH_ATTEMPTS, url, e)
                if attempt == IMAGE_FETCH_ATTEMPTS - 1:
                    # Two stalls in a row on the same image — refresh the CF
                    # session before the final attempt.
                    try:
                        async with self._solve_lock:
                            await self._solve(chapter_url)
                    except Exception:
                        pass
                await asyncio.sleep(attempt)
        raise RuntimeError(f"could not fetch {url} after {IMAGE_FETCH_ATTEMPTS} attempts: {last_err}")

    async def fetch_chapter_pages(self, chapter_url: str, save_dir: Path) -> int:
        """Download every page of a chapter into save_dir, skipping files
        already on disk so an interrupted chapter resumes instead of
        restarting. Returns the total page count of the chapter."""
        await self._ensure_started()
        async with self._lock:
            ok = await self._solve(chapter_url)
            if not ok:
                raise RuntimeError(f"CF challenge not solved at {chapter_url}")
            html = await self._page.content()
            urls = sorted(set(IMAGE_URL_RE.findall(html)),
                          key=lambda u: _natural_sort_key(u.rsplit('/', 1)[-1]))
            if not urls:
                raise RuntimeError(f"no image URLs in {chapter_url}")

            save_dir.mkdir(parents=True, exist_ok=True)
            sem = asyncio.Semaphore(IMAGE_CONCURRENCY)

            async def _download(u: str):
                name = u.rsplit('/', 1)[-1].split('?')[0]
                out_path = save_dir / name
                if out_path.exists() and out_path.stat().st_size > 0:
                    return
                async with sem:
                    body = await self._fetch_image(u, chapter_url)
                    out_path.write_bytes(body)
                    # Small jitter per fetch keeps the burst rate below
                    # Cloudflare's adaptive rate-limit.
                    await asyncio.sleep(0.15)

            results = await asyncio.gather(*(_download(u) for u in urls),
                                           return_exceptions=True)
            errors = [r for r in results if isinstance(r, BaseException)]
            if errors:
                raise errors[0]
            return len(urls)
