#!/usr/bin/env python3
"""URL parsing + chapter list cache for RipRaven.

All ravenscans.org and cdnN.ravenscans.org endpoints are behind a Cloudflare
managed challenge, so the server cannot fetch them. Chapter discovery and image
fetching now happen client-side via the Tampermonkey userscript at
`static/ripraven.user.js`. This module is reduced to pure URL parsing and the
on-disk chapter list cache that the userscript writes into.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


CHAPTER_URL_RE = re.compile(r'/([^/]+)-chapter-(\d+(?:-\d+)?)/?$')


def parse_chapter_url(url: str) -> Optional[dict]:
    """Extract series slug + chapter number from a ravenscans chapter URL.

    Returns ``{'series_slug': 'past-life-returner', 'series_name': 'Past_Life_Returner',
    'chapter_num': '1.1', 'series_url': 'https://ravenscans.org/manga/past-life-returner/'}``
    or None if the URL doesn't look like a chapter.

    Fractional chapter slugs use hyphen form (``chapter-1-1`` for 1.1).
    """
    path = urlparse(url).path
    m = CHAPTER_URL_RE.search(path)
    if not m:
        return None
    series_slug = m.group(1)
    chapter_num = m.group(2).replace('-', '.')
    return {
        'series_slug': series_slug,
        'series_name': series_slug.replace('-', '_').title().replace(' ', '_'),
        'chapter_num': chapter_num,
        'series_url': f"https://ravenscans.org/manga/{series_slug}/",
    }


class ChapterListCache:
    """Persists `{series_name -> [{number, url}, ...]}` for tracked series.

    Populated by the userscript via POST /api/ripraven/series/<slug>/chapter-list.
    Read by the queue endpoint to decide what's missing on disk.
    """

    def __init__(self, cache_dir: str | Path = "../data/ripraven"):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "chapter_cache.json"
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("⚠️ Could not load chapter cache: %s", e)
        return {}

    def _save_cache(self):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning("⚠️ Could not save chapter cache: %s", e)

    def _normalize_series_key(self, series_name: str) -> str:
        return series_name.lower().replace(' ', '_').replace('-', '_')

    def get_chapters(self, series_name: str) -> Optional[List[dict]]:
        entry = self._cache.get(self._normalize_series_key(series_name))
        return entry.get('chapters', []) if entry else None

    def set_chapters(self, series_name: str, chapters: List[dict], series_url: str = None):
        # Sort 1, 1.1, 1.2, 2, 10, ... by numeric value.
        def sort_key(ch):
            try:
                parts = str(ch['number']).split('.')
                return (float(parts[0]), float(parts[1]) if len(parts) > 1 else 0)
            except ValueError:
                return (0.0, 0.0)
        chapters_sorted = sorted(chapters, key=sort_key)

        self._cache[self._normalize_series_key(series_name)] = {
            'chapters': chapters_sorted,
            'series_url': series_url,
            'last_updated': datetime.now().isoformat(),
        }
        self._save_cache()

    def get_series_url(self, series_name: str) -> Optional[str]:
        entry = self._cache.get(self._normalize_series_key(series_name))
        return entry.get('series_url') if entry else None

    def get_chapter_url(self, series_name: str, chapter_num: str) -> Optional[str]:
        for ch in (self.get_chapters(series_name) or []):
            if str(ch['number']) == str(chapter_num):
                return ch.get('url')
        return None

    def get_next_chapters(self, series_name: str, current_chapter: str, count: int = 3) -> List[str]:
        chapters = self.get_chapters(series_name) or []
        nums = [ch['number'] for ch in chapters]
        try:
            idx = nums.index(current_chapter)
        except ValueError:
            return []
        return nums[idx + 1: idx + 1 + count]
