"""Ravenscans source.

The site sits behind a Cloudflare managed challenge. Patchright clears it in
headed Chrome under Xvfb, then the clearance cookie and matching user agent go
back to httpx for normal page and image requests. Older ravenscans.net URLs
301 to their .org equivalents as long as redirects are followed.

Series pages carry chapter numbers in `<li data-num="12.1">`; chapter pages
carry ordered images in a `ts_reader.run({...})` JSON blob.
"""

import asyncio
import json
import logging
import re
from typing import List, Optional

import httpx

from .cloudflare import fetch_with_clearance
from .sources import (  # re-exported for the worker and existing callers
    HOST_DOWN_S,
    IMAGE_ATTEMPTS,
    REQUEST_TIMEOUT_S,
    USER_AGENT,
    ChapterSource,
    ImageFetchError,
    SourceUnavailable,
    describe_exc,
)

logger = logging.getLogger(__name__)

RAVENSCANS_HOME = 'https://ravenscans.org/'

# Match only the word `chapter-`: the surrounding path has changed twice.
CHAPTER_LI_RE = re.compile(r'<li[^>]*\bdata-num="([^"]+)"[^>]*>')
HREF_RE = re.compile(r'<a[^>]+href="([^"]+)"')
TS_READER_RE = re.compile(r'ts_reader\.run\((\{.*?\})\);', re.S)


def parse_chapter_list(html: str) -> List[dict]:
    """Extract `[{'number': '12.1', 'url': ...}, ...]` from a series page."""
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


def _is_cloudflare_challenge(response: httpx.Response) -> bool:
    return response.status_code in (403, 503) and (
        response.headers.get('cf-mitigated') == 'challenge'
        or '<title>Just a moment' in response.text[:4096]
    )


class RavenScraper(ChapterSource):
    name = 'ravenscans'
    home = RAVENSCANS_HOME

    def __init__(self):
        super().__init__()
        self._challenge_lock: Optional[asyncio.Lock] = None

    def _get_challenge_lock(self) -> asyncio.Lock:
        if self._challenge_lock is None:
            self._challenge_lock = asyncio.Lock()
        return self._challenge_lock

    async def _get_text(self, url: str) -> str:
        response = await self._get_client().get(url)
        if not _is_cloudflare_challenge(response):
            response.raise_for_status()
            return response.text

        # One Chrome instance clears a challenge shared by every series.
        async with self._get_challenge_lock():
            response = await self._get_client().get(url)
            if not _is_cloudflare_challenge(response):
                response.raise_for_status()
                return response.text
            logger.info("🦅 clearing Cloudflare challenge for %s", url)
            html, user_agent, cookies = await fetch_with_clearance(
                url, navigation_timeout_s=REQUEST_TIMEOUT_S,
            )
            client = self._get_client()
            client.headers['User-Agent'] = user_agent
            for cookie in cookies:
                client.cookies.set(
                    cookie['name'], cookie['value'],
                    domain=cookie['domain'], path=cookie['path'],
                )
            return html

    async def scrape_chapter_list(self, series_url: str) -> List[dict]:
        chapters = parse_chapter_list(await self._get_text(series_url))
        if not chapters:
            raise RuntimeError(f"no chapters parsed from {series_url}")
        return chapters

    async def chapter_image_urls(self, chapter_url: str) -> List[str]:
        return parse_chapter_images(await self._get_text(chapter_url))
