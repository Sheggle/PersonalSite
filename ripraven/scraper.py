"""Scraper for ravenscans.

The site serves from ravenscans.org. Plain HTTP gets through — pages and the
`cdnN.ravenscans.org` images alike; there is no managed challenge. Older
`ravenscans.net` URLs still sitting in the caches 301 to their .org
equivalents, so they keep resolving as long as redirects are followed.

Two page shapes matter:

  series page   https://ravenscans.org/manga/<slug>/
      Chapter list as `<li data-num="12.1"> … <a href=".../<slug>-chapter-12-1/">`.
      `data-num` is the chapter number (fractional chapters included) and is
      the only place it is stated; the whole list is on one page, no pagination.

  chapter page  https://ravenscans.org/<slug>-chapter-96/
      Page images live in the `ts_reader.run({...})` JSON blob, already in
      reading order. Mixed extensions within one chapter are normal.
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

RAVENSCANS_HOME = 'https://ravenscans.org/'
USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# Chapter list items. The number lives only in `data-num`; the link shape has
# changed before (`/chapter-<id>/` vs `-chapter-<n>/`), so match on the word
# alone and bound the search to the item to avoid running past it.
CHAPTER_LI_RE = re.compile(r'<li[^>]*\bdata-num="([^"]+)"[^>]*>')
HREF_RE = re.compile(r'<a[^>]+href="([^"]+)"')

TS_READER_RE = re.compile(r'ts_reader\.run\((\{.*?\})\);', re.S)

REQUEST_TIMEOUT_S = 30
# Images get a tighter deadline than pages. A CDN node whose origin is down
# answers 522 only after ~20s, and because a request holds an IMAGE_CONCURRENCY
# slot while it waits, a handful of dead images can stall every series at once.
# A page image that has not started arriving in 10s is not coming.
IMAGE_TIMEOUT_S = 10
# Bounds the total number of in-flight image requests for the whole process,
# not per chapter — several series download in parallel and this is what keeps
# their combined load on a volunteer scanlation host reasonable.
IMAGE_CONCURRENCY = 12
IMAGE_ATTEMPTS = 3
# How long a CDN host stays written off after a whole chapter failed on it.
# Individual nodes go down for hours: cdn3 can be returning 522 for every
# series it holds while cdn1 and cdn2 serve in under a second. Probing it once
# per chapter costs 33s of timeouts each time, which is the difference between
# walking a dead run of chapters in seconds and taking all afternoon over it.
HOST_DOWN_S = 10 * 60


class SourceUnavailable(RuntimeError):
    """Skipped without a request: every page of this chapter sits on a host
    that just failed a whole chapter."""


class ImageFetchError(RuntimeError):
    """An image failed; only connection failures and 5xx suggest a host outage."""

    def __init__(self, message: str, *, host_unavailable: bool):
        super().__init__(message)
        self.host_unavailable = host_unavailable


def describe_exc(e: BaseException) -> str:
    """`str(e)` alone is useless for the failures that actually happen here:
    httpx timeout exceptions carry an empty message, so an error built from
    them reads "could not fetch <url> after 3 attempts:" and names nothing.
    Always lead with the class."""
    text = str(e).strip()
    return f"{type(e).__name__}: {text}" if text else type(e).__name__


def parse_chapter_list(html: str) -> List[dict]:
    """Extract `[{'number': '12.1', 'url': ...}, ...]` from a series page.

    Each `<li data-num=...>` is read separately, taking the first chapter link
    inside it, so an item without a link cannot borrow the next item's URL.
    """
    items = list(CHAPTER_LI_RE.finditer(html))
    seen, chapters = set(), []
    for i, m in enumerate(items):
        num = m.group(1).strip()
        if not num or num in seen:
            continue
        end = items[i + 1].start() if i + 1 < len(items) else len(html)
        url = next((h for h in HREF_RE.findall(html[m.end():end]) if 'chapter-' in h), None)
        if not url:
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
        self._image_sem: Optional[asyncio.Semaphore] = None
        # host -> when it last failed a whole chapter.
        self._host_down: Dict[str, float] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                # Stale .net URLs are still all over the cache; let them redirect.
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT_S,
                headers={'User-Agent': USER_AGENT, 'Referer': RAVENSCANS_HOME},
                limits=httpx.Limits(
                    max_connections=IMAGE_CONCURRENCY + 4,
                    max_keepalive_connections=IMAGE_CONCURRENCY + 4,
                ),
            )
        return self._client

    def _get_image_sem(self) -> asyncio.Semaphore:
        # Built lazily: it must belong to the loop the worker runs on.
        if self._image_sem is None:
            self._image_sem = asyncio.Semaphore(IMAGE_CONCURRENCY)
        return self._image_sem

    def _hosts_down(self, hosts: set) -> list:
        cutoff = time.time() - HOST_DOWN_S
        return sorted(h for h in hosts if self._host_down.get(h, 0) > cutoff)

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
                r = await self._get_client().get(url, timeout=IMAGE_TIMEOUT_S)
                r.raise_for_status()
                if not r.content:
                    raise RuntimeError(f"empty body for {url}")
                return r.content
            except Exception as e:
                last_err = e
                logger.warning("🦅 image fetch %d/%d failed for %s: %s",
                               attempt, IMAGE_ATTEMPTS, url, describe_exc(e))
                if attempt < IMAGE_ATTEMPTS:
                    await asyncio.sleep(attempt)
        # Cause first: this string is what the home page shows, and "could not
        # fetch <url> after 3 attempts:" told the reader nothing about why.
        host_unavailable = (
            isinstance(last_err, (httpx.NetworkError, httpx.TimeoutException))
            and not isinstance(last_err, httpx.PoolTimeout)
        ) or (
            isinstance(last_err, httpx.HTTPStatusError)
            and last_err.response.status_code >= 500
        )
        raise ImageFetchError(
            f"{describe_exc(last_err)} after {IMAGE_ATTEMPTS} attempts on {url}",
            host_unavailable=host_unavailable,
        ) from last_err

    async def fetch_chapter_pages(self, chapter_url: str, save_dir: Path) -> int:
        """Download every page of a chapter into save_dir, skipping files
        already on disk so an interrupted chapter resumes instead of
        restarting. Returns the total page count of the chapter."""
        urls = parse_chapter_images(await self._get_text(chapter_url))

        hosts = {urlparse(u).netloc for u in urls}
        down = self._hosts_down(hosts)
        if down and len(down) == len(hosts):
            raise SourceUnavailable(f"{', '.join(down)} unreachable")

        save_dir.mkdir(parents=True, exist_ok=True)
        sem = self._get_image_sem()

        # The chapter is lost the moment one page is unfetchable, and when a
        # CDN node is down every page of the chapter is unfetchable together.
        # Without this flag the other 150 pages each still burn three attempts
        # against a dead host while holding an IMAGE_CONCURRENCY slot, so one
        # broken chapter starves every other series for minutes.
        failures: List[BaseException] = []
        fetched = 0

        async def _download(idx: int, u: str):
            nonlocal fetched
            # Keep the CDN's own filename (0.webp, 1.webp, …): the reader
            # natural-sorts filenames, and reusing the remote name is what
            # lets an interrupted chapter resume instead of redownloading.
            name = u.rsplit('/', 1)[-1].split('?')[0] or f"{idx:03d}.jpg"
            out_path = save_dir / name
            if out_path.exists() and out_path.stat().st_size > 0:
                return
            if failures:
                return
            try:
                async with sem:
                    if failures:  # may have waited a long time for the slot
                        return
                    data = await self._fetch_image(u)
                    fetched += 1
                # A failed write must not leave a nonempty partial page that
                # the next pass mistakes for a successfully downloaded image.
                temporary = out_path.with_name(out_path.name + '.part')
                try:
                    temporary.write_bytes(data)
                    temporary.replace(out_path)
                finally:
                    temporary.unlink(missing_ok=True)
            except Exception as e:
                # Every failure lands here, a full disk as much as a dead CDN
                # node: a chapter missing a page must never be marked complete.
                failures.append(e)
                raise

        await asyncio.gather(
            *(_download(i, u) for i, u in enumerate(urls)),
            return_exceptions=True,
        )
        if failures:
            # A 404 or a local write error says nothing about host health.
            # Even a timeout is not a host outage if other pages arrived.
            if len(hosts) == 1 and not fetched and all(
                isinstance(e, ImageFetchError) and e.host_unavailable
                for e in failures
            ):
                self._host_down[next(iter(hosts))] = time.time()
            for error in failures:
                if isinstance(error, OSError):
                    raise error
            raise failures[0]
        for h in hosts:
            self._host_down.pop(h, None)
        return len(urls)
