"""Tracked-series state + queue logic for the browser-side downloader.

A "tracked" series is one the user has imported. The Tampermonkey userscript
running on ravenscans.org polls GET /api/ripraven/queue, gets a small batch of
work items (either "scrape the chapter list for series X" or "download chapter
Y of series X"), does the work, and POSTs results back. Claim tokens prevent
two open tabs from racing on the same chapter.
"""

import json
import logging
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


CLAIM_TTL_SECONDS = 300


class TrackingState:
    """Persisted set of tracked series + in-memory claim leases.

    File schema (`tracking.json`):
        {slug: {series_name, series_slug, series_url, source_url, added}, ...}

    Claims live only in memory; a process restart re-opens every chapter for
    work, which is fine — at worst, two tabs duplicate one chapter before TTL.
    """

    def __init__(self, data_dir: str | Path = "../data/ripraven"):
        self.path = Path(data_dir) / "tracking.json"
        self._state: dict = self._load()
        self._claims: dict[str, dict] = {}

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("⚠️ Could not load tracking state: %s", e)
        return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.json.tmp')
        with open(tmp, 'w') as f:
            json.dump(self._state, f, indent=2)
        tmp.replace(self.path)

    def add(self, series_slug: str, series_name: str, series_url: str, source_url: str):
        if series_slug in self._state:
            return
        self._state[series_slug] = {
            'series_name': series_name,
            'series_slug': series_slug,
            'series_url': series_url,
            'source_url': source_url,
            'added': datetime.now().isoformat(),
        }
        self._save()

    def remove(self, series_slug: str):
        if series_slug in self._state:
            del self._state[series_slug]
            self._save()

    def list(self) -> dict:
        return dict(self._state)

    # ---- claim handling ----------------------------------------------------

    def _gc_claims(self):
        now = time.time()
        self._claims = {t: c for t, c in self._claims.items() if c['expires'] > now}

    def _is_claimed(self, item_id: str) -> bool:
        self._gc_claims()
        return any(c['item_id'] == item_id for c in self._claims.values())

    def _claim(self, item_id: str) -> str:
        token = secrets.token_urlsafe(16)
        self._claims[token] = {'item_id': item_id, 'expires': time.time() + CLAIM_TTL_SECONDS}
        return token

    def release(self, token: str):
        self._claims.pop(token, None)

    # ---- queue building ----------------------------------------------------

    def build_queue(
        self,
        chapter_cache,
        chapter_is_complete: Callable[[str, str], bool],
        limit: int = 1,
    ) -> List[dict]:
        """Return up to `limit` actionable work items across all tracked series.

        For each tracked series in insertion order:
        - If we have no cached chapter list, emit a `chapter-list` task.
        - Otherwise emit `chapter` tasks for the missing chapters in series
          order (oldest missing first), so backfill reads ch 1 → N.

        Already-claimed item ids are skipped. Items returned carry a fresh
        claim_token; failures must POST /queue/release with it.
        """
        items: List[dict] = []

        for slug, info in self._state.items():
            if len(items) >= limit:
                break

            series_name = info['series_name']

            chapters = chapter_cache.get_chapters(series_name)
            if not chapters:
                item_id = f"{slug}/__list__"
                if self._is_claimed(item_id):
                    continue
                items.append({
                    'type': 'chapter-list',
                    'series_slug': slug,
                    'series_name': series_name,
                    'series_url': info['series_url'],
                    'item_id': item_id,
                })
                continue

            # Oldest first — backfill in reading order from chapter 1 up.
            for ch in chapters:
                if len(items) >= limit:
                    break
                ch_num = str(ch['number'])
                if chapter_is_complete(series_name, ch_num):
                    continue
                item_id = f"{slug}/{ch_num}"
                if self._is_claimed(item_id):
                    continue
                items.append({
                    'type': 'chapter',
                    'series_slug': slug,
                    'series_name': series_name,
                    'chapter_num': ch_num,
                    'chapter_url': ch['url'],
                    'item_id': item_id,
                })

        # Issue claims after selection.
        for it in items:
            it['claim_token'] = self._claim(it.pop('item_id'))

        return items

    def status(self, chapter_cache, chapter_is_complete: Callable[[str, str], bool]) -> List[dict]:
        """Per-series progress snapshot for the home page UI."""
        out = []
        for slug, info in self._state.items():
            chapters = chapter_cache.get_chapters(info['series_name']) or []
            total = len(chapters)
            done = sum(1 for ch in chapters if chapter_is_complete(info['series_name'], str(ch['number'])))
            out.append({
                'series_slug': slug,
                'series_name': info['series_name'],
                'series_url': info['series_url'],
                'total_chapters': total,
                'downloaded_chapters': done,
                'has_chapter_list': total > 0,
                'added': info.get('added'),
            })
        return out
