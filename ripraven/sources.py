"""Chapter sources and the small fallback coordinator used by the worker.

A source knows how to list a series' chapters and resolve one chapter's image
URLs. ChapterSource owns the shared download machinery; MultiSourceScraper keeps
ravenscans as the catalog and consults other sources only after a chapter fails.
"""

import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
REQUEST_TIMEOUT_S = 30
# A dead image host must not hold the process-wide image slots for long.
IMAGE_TIMEOUT_S = 10
IMAGE_CONCURRENCY = 12
IMAGE_ATTEMPTS = 3
HOST_DOWN_S = 10 * 60
FALLBACK_CHAPTER_LIST_TTL_S = 6 * 3600
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
PARTIAL_SOURCE_MARKER = 'partial_source'


class SourceUnavailable(RuntimeError):
    """Skipped without a request: every page sits on a host known to be down."""


class ImageFetchError(RuntimeError):
    """An image failed; only connection failures and 5xx suggest a host outage."""

    def __init__(self, message: str, *, host_unavailable: bool):
        super().__init__(message)
        self.host_unavailable = host_unavailable


def describe_exc(e: BaseException) -> str:
    """Include the exception class: httpx timeout messages are often empty."""
    text = str(e).strip()
    return f"{type(e).__name__}: {text}" if text else type(e).__name__


class ChapterSource:
    name = 'source'
    home = ''

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._image_sem: Optional[asyncio.Semaphore] = None
        # host -> when it last failed a whole chapter.
        self._host_down: Dict[str, float] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT_S,
                headers={'User-Agent': USER_AGENT, 'Referer': self.home},
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
        response = await self._get_client().get(url)
        response.raise_for_status()
        return response.text

    async def scrape_chapter_list(self, series_url: str) -> List[dict]:
        raise NotImplementedError

    async def chapter_image_urls(self, chapter_url: str) -> List[str]:
        raise NotImplementedError

    async def find_series(self, title: str) -> Optional[str]:
        """Return an unambiguous series URL, or None when there is no match."""
        return None

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
                logger.warning("🦅 %s image fetch %d/%d failed for %s: %s",
                               self.name, attempt, IMAGE_ATTEMPTS, url, describe_exc(e))
                if attempt < IMAGE_ATTEMPTS:
                    await asyncio.sleep(attempt)
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
        """Download a complete chapter, resuming files already on disk."""
        urls = await self.chapter_image_urls(chapter_url)
        if not urls:
            raise RuntimeError(f"no page images on {chapter_url}")

        hosts = {urlparse(u).netloc for u in urls}
        down = self._hosts_down(hosts)
        if down and len(down) == len(hosts):
            raise SourceUnavailable(f"{', '.join(down)} unreachable")

        save_dir.mkdir(parents=True, exist_ok=True)
        sem = self._get_image_sem()
        failures: List[BaseException] = []
        fetched = 0

        async def _download(idx: int, u: str):
            nonlocal fetched
            name = u.rsplit('/', 1)[-1].split('?')[0] or f"{idx:03d}.jpg"
            out_path = save_dir / name
            if out_path.exists() and out_path.stat().st_size > 0:
                return
            if failures:
                return
            try:
                async with sem:
                    if failures:
                        return
                    data = await self._fetch_image(u)
                    fetched += 1
                temporary = out_path.with_name(out_path.name + '.part')
                try:
                    temporary.write_bytes(data)
                    temporary.replace(out_path)
                finally:
                    temporary.unlink(missing_ok=True)
            except Exception as e:
                failures.append(e)
                raise

        await asyncio.gather(
            *(_download(i, u) for i, u in enumerate(urls)),
            return_exceptions=True,
        )
        if failures:
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


class _AstroIslands(HTMLParser):
    def __init__(self):
        super().__init__()
        self.props = []

    def handle_starttag(self, tag, attrs):
        if tag != 'astro-island':
            return
        values = dict(attrs)
        if values.get('component-url') and values.get('props'):
            self.props.append((values['component-url'], values['props']))


def _decode_astro(value):
    """Decode the small subset of devalue used by Astro island props."""
    if isinstance(value, dict):
        return {k: _decode_astro(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) == 2 and value[0] == 0:
            return _decode_astro(value[1])
        if len(value) == 2 and value[0] == 1:
            return [_decode_astro(v) for v in value[1]]
        return [_decode_astro(v) for v in value]
    return value


def _astro_props(html: str, component: str) -> dict:
    parser = _AstroIslands()
    parser.feed(html)
    for url, raw in parser.props:
        if component in url:
            return _decode_astro(json.loads(raw))
    raise RuntimeError(f"no {component} props on Asura page")


def parse_asura_chapter_list(html: str, series_url: str) -> List[dict]:
    props = _astro_props(html, 'ChapterList')
    chapters = []
    for chapter in props.get('chapters') or []:
        number = chapter.get('number')
        if number is None:
            continue
        chapters.append({
            'number': str(number),
            'url': f"{series_url.rstrip('/')}/chapter/{number}",
        })
    if not chapters:
        raise RuntimeError("Asura chapter list carries no chapters")
    return chapters


def parse_asura_chapter_images(html: str) -> List[str]:
    props = _astro_props(html, 'ChapterReader')
    pages = [p.get('url') for p in props.get('pages') or []]
    if not all(pages):
        raise RuntimeError("Asura reader has missing page URLs")
    if not pages:
        raise RuntimeError("Asura reader carries no pages")
    return pages


def normalize_title(title: str) -> str:
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '', ascii_title.lower())


def match_series(title: str, candidates: List[dict]) -> Optional[dict]:
    """Exact title/alias matching only; ambiguous matches need an override."""
    wanted = normalize_title(title)
    matches = []
    for candidate in candidates:
        titles = [candidate.get('title') or ''] + (candidate.get('alt_titles') or [])
        if wanted and wanted in {normalize_title(t) for t in titles}:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


class AsuraScraper(ChapterSource):
    name = 'asura'
    home = 'https://asurascans.com/'
    api_home = 'https://api.asurascans.com'

    async def find_series(self, title: str) -> Optional[str]:
        response = await self._get_client().get(
            f'{self.api_home}/api/search', params={'q': title},
        )
        response.raise_for_status()
        match = match_series(title, response.json().get('data') or [])
        if not match or not match.get('public_url'):
            return None
        return urljoin(self.home, match['public_url'])

    async def scrape_chapter_list(self, series_url: str) -> List[dict]:
        return parse_asura_chapter_list(await self._get_text(series_url), series_url)

    async def chapter_image_urls(self, chapter_url: str) -> List[str]:
        return parse_asura_chapter_images(await self._get_text(chapter_url))


@dataclass
class DownloadedChapter:
    page_count: int
    source: str
    url: str


def _chapter_number(value) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal('-999999999')


def clear_partial_images(chapter_dir: Path):
    """Do not mix pages from different scanlations in an incomplete chapter."""
    if not chapter_dir.exists():
        return
    for path in chapter_dir.iterdir():
        if path.is_file() and (path.suffix.lower() in IMAGE_EXTENSIONS or path.name.endswith('.part')):
            path.unlink()


class MultiSourceScraper:
    """Raven first; resolve and try each fallback only after Raven fails."""

    def __init__(self, primary: ChapterSource, fallbacks: List[ChapterSource]):
        self.primary = primary
        self.fallbacks = fallbacks
        self.sources = [primary] + fallbacks
        # All sources share the one process-wide image budget.
        shared_sem = primary._get_image_sem()
        for source in self.sources:
            source._image_sem = shared_sem
        self._series_urls = {}
        self._chapter_lists = {}

    async def close(self):
        await asyncio.gather(*(source.close() for source in self.sources))

    async def scrape_chapter_list(self, series_url: str) -> List[dict]:
        return await self.primary.scrape_chapter_list(series_url)

    async def _series_url(self, source: ChapterSource, info: dict) -> Optional[str]:
        key = (source.name, info['series_slug'])
        if key not in self._series_urls:
            overrides = info.get('source_urls') or {}
            try:
                if source.name in overrides:
                    value = overrides[source.name]
                    self._series_urls[key] = urljoin(source.home, value) if value else None
                else:
                    title = info['series_name'].replace('_', ' ')
                    self._series_urls[key] = await source.find_series(title)
            except Exception as e:
                logger.warning("🦅 %s series lookup failed for %s: %s",
                               source.name, info['series_name'], describe_exc(e))
                # A real negative match is cached; a transient API failure is
                # retried on a later chapter rather than disabling the source.
                return None
        return self._series_urls[key]

    async def _chapter_url(self, source: ChapterSource, info: dict,
                           chapter_number: str) -> Optional[str]:
        series_url = await self._series_url(source, info)
        if not series_url:
            return None
        key = (source.name, series_url)
        cached = self._chapter_lists.get(key)
        if not cached or time.time() - cached[0] >= FALLBACK_CHAPTER_LIST_TTL_S:
            chapters = await source.scrape_chapter_list(series_url)
            self._chapter_lists[key] = (time.time(), chapters)
        wanted = _chapter_number(chapter_number)
        return next(
            (ch['url'] for ch in self._chapter_lists[key][1]
             if _chapter_number(ch['number']) == wanted),
            None,
        )

    def _prepare_source(self, source: ChapterSource, save_dir: Path):
        """Resume same-source pages, but never mix two scanlations."""
        marker = save_dir / PARTIAL_SOURCE_MARKER
        try:
            previous = marker.read_text().strip()
        except FileNotFoundError:
            previous = None
        if source is not self.primary or (previous and previous != source.name):
            clear_partial_images(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text(source.name)

    async def fetch_chapter_pages(self, chapter: dict, info: dict,
                                  save_dir: Path) -> DownloadedChapter:
        errors = []
        primary_error = None
        try:
            self._prepare_source(self.primary, save_dir)
            count = await self.primary.fetch_chapter_pages(chapter['url'], save_dir)
            return DownloadedChapter(count, self.primary.name, chapter['url'])
        except asyncio.CancelledError:
            raise
        except OSError:
            raise
        except Exception as e:
            primary_error = e
            errors.append(f"{self.primary.name}: {describe_exc(e)}")

        fallback_requested = False
        for source in self.fallbacks:
            try:
                url = await self._chapter_url(source, info, str(chapter['number']))
            except asyncio.CancelledError:
                raise
            except OSError:
                raise
            except Exception as e:
                errors.append(f"{source.name}: {describe_exc(e)}")
                continue
            if not url:
                errors.append(f"{source.name}: no exact series/chapter match")
                continue
            logger.info("🦅 trying %s for %s ch %s",
                        source.name, info['series_name'], chapter['number'])
            self._prepare_source(source, save_dir)
            fallback_requested = True
            try:
                count = await source.fetch_chapter_pages(url, save_dir)
                return DownloadedChapter(count, source.name, url)
            except asyncio.CancelledError:
                raise
            except OSError:
                raise
            except Exception as e:
                errors.append(f"{source.name}: {describe_exc(e)}")

        if isinstance(primary_error, SourceUnavailable) and not fallback_requested:
            raise SourceUnavailable('; '.join(errors))
        raise RuntimeError('; '.join(errors))
