"""Scraper for ravenscans.

The site moved from ravenscans.org to ravenscans.net and no longer serves a
Cloudflare managed challenge, so plain HTTP gets through — pages and the
`cdnN.ravenscans.org` images alike. Old .org URLs 301 to their .net
equivalents, so cached pre-move URLs keep resolving as long as redirects are
followed.

Two page shapes matter:

  series page   https://ravenscans.net/series/<slug>/
      Chapter list as `<li data-num="12.1"> … <a href=".../chapter-<id>/">`.
      `data-num` is the chapter number (fractional chapters included); the
      whole list is on one page, no pagination.

  chapter page  https://ravenscans.net/series/<slug>/chapter-<id>/
      `chapter-<id>` is an opaque post id, NOT the chapter number — the number
      only exists on the series page. Page images live in the
      `ts_reader.run({...})` JSON blob, already in reading order.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

RAVENSCANS_HOME = 'https://ravenscans.net/'
USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

CHAPTER_ITEM_RE = re.compile(
    r'<li[^>]*\bdata-num="([^"]+)"[^>]*>.*?<a[^>]+href="([^"]*/chapter-[^"]*?)"',
    re.S,
)
TS_READER_RE = re.compile(r'ts_reader\.run\((\{.*?\})\);', re.S)

REQUEST_TIMEOUT_S = 30
IMAGE_CONCURRENCY = 4
IMAGE_ATTEMPTS = 3
# Small per-image pause. The site is a volunteer scanlation host; there is no
# rate limit forcing this, it just keeps us from hammering it.
PER_IMAGE_DELAY_S = 0.1


def parse_chapter_list(html: str) -> List[dict]:
    """Extract `[{'number': '12.1', 'url': ...}, ...]` from a series page."""
    seen, chapters = set(), []
    for num, url in CHAPTER_ITEM_RE.findall(html):
        num = num.strip()
        if not num or num in seen:
            continue
        seen.add(num)
        chapters.append({'number': num, 'url': url})
    return chapters


def parse_chapter_images(html: str) -> List[str]:
    """Extract the page image URLs from a chapter page's ts_reader payload."""
    m = TS_READER_RE.search(html)
    if not m:
        raise RuntimeError("no ts_reader payload on chapter page")
    data = json.loads(m.group(1))
    for source in data.get('sources') or []:
        images = [u for u in (source.get('images') or []) if u]
        if images:
            return images
    raise RuntimeError("ts_reader payload carries no images")


class RavenScraper:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                # Pre-move URLs are still all over the cache; let them redirect.
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT_S,
                headers={'User-Agent': USER_AGENT, 'Referer': RAVENSCANS_HOME},
            )
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_text(self, url: str) -> str:
        r = await self._get_client().get(url)
        r.raise_for_status()
        return r.text

    async def scrape_chapter_list(self, series_url: str) -> List[dict]:
        chapters = parse_chapter_list(await self._get_text(series_url))
        if not chapters:
            raise RuntimeError(f"no chapters parsed from {series_url}")
        return chapters

    async def _fetch_image(self, url: str) -> bytes:
        last_err: Optional[Exception] = None
        for attempt in range(1, IMAGE_ATTEMPTS + 1):
            try:
                r = await self._get_client().get(url)
                r.raise_for_status()
                if not r.content:
                    raise RuntimeError(f"empty body for {url}")
                return r.content
            except Exception as e:
                last_err = e
                logger.warning("🦅 image fetch %d/%d failed for %s: %s",
                               attempt, IMAGE_ATTEMPTS, url, e)
                await asyncio.sleep(attempt)
        raise RuntimeError(f"could not fetch {url} after {IMAGE_ATTEMPTS} attempts: {last_err}")

    async def fetch_chapter_pages(self, chapter_url: str, save_dir: Path) -> int:
        """Download every page of a chapter into save_dir, skipping files
        already on disk so an interrupted chapter resumes instead of
        restarting. Returns the total page count of the chapter."""
        urls = parse_chapter_images(await self._get_text(chapter_url))

        save_dir.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(IMAGE_CONCURRENCY)

        async def _download(idx: int, u: str):
            # Keep the CDN's own filename (0.webp, 1.webp, …): the reader
            # natural-sorts filenames, and reusing the remote name is what
            # lets an interrupted chapter resume instead of redownloading.
            name = u.rsplit('/', 1)[-1].split('?')[0] or f"{idx:03d}.jpg"
            out_path = save_dir / name
            if out_path.exists() and out_path.stat().st_size > 0:
                return
            async with sem:
                out_path.write_bytes(await self._fetch_image(u))
                await asyncio.sleep(PER_IMAGE_DELAY_S)

        results = await asyncio.gather(
            *(_download(i, u) for i, u in enumerate(urls)),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise errors[0]
        return len(urls)
