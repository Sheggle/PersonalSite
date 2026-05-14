"""Background worker: drive CFScraper against the TrackingState.

Walks each tracked series in insertion order, scrapes a missing chapter list
or downloads one missing chapter (oldest first) per iteration, then loops.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from .scraper import CFScraper
from .pattern_finder import ChapterListCache
from .tracking import TrackingState

logger = logging.getLogger(__name__)

IDLE_SLEEP_S = 60
ERROR_SLEEP_S = 30
WORK_SLEEP_S = 3


async def _one_cycle(scraper: CFScraper,
                     tracking: TrackingState,
                     chapter_cache: ChapterListCache,
                     downloads_dir: Path,
                     is_complete: Callable[[str, str], bool]) -> bool:
    for slug, info in tracking.list().items():
        series_name = info['series_name']
        chapters = chapter_cache.get_chapters(series_name)
        if not chapters:
            logger.info("📚 scraping chapter list for %s", series_name)
            new = await scraper.scrape_chapter_list(info['series_url'])
            chapter_cache.set_chapters(series_name, new, info['series_url'])
            logger.info("📚 cached %d chapters for %s", len(new), series_name)
            return True
        for ch in chapters:
            ch_num = str(ch['number'])
            if is_complete(series_name, ch_num):
                continue
            logger.info("📥 fetching %s ch %s", series_name, ch_num)
            pages = await scraper.fetch_chapter_pages(ch['url'])
            chapter_dir = downloads_dir / series_name / f"chapter_{ch_num}"
            chapter_dir.mkdir(parents=True, exist_ok=True)
            for fname, data in pages:
                (chapter_dir / fname).write_bytes(data)
            (chapter_dir / "completed").write_text(datetime.now().isoformat())
            logger.info("✅ %s ch %s: saved %d pages", series_name, ch_num, len(pages))
            return True
    return False


async def run_worker(scraper: CFScraper,
                     tracking: TrackingState,
                     chapter_cache: ChapterListCache,
                     downloads_dir: Path,
                     is_complete: Callable[[str, str], bool]):
    logger.info("🦅 ripraven worker: starting")
    while True:
        try:
            did_work = await _one_cycle(scraper, tracking, chapter_cache, downloads_dir, is_complete)
            await asyncio.sleep(WORK_SLEEP_S if did_work else IDLE_SLEEP_S)
        except asyncio.CancelledError:
            logger.info("🦅 ripraven worker: cancelled")
            raise
        except Exception:
            logger.exception("worker cycle error")
            await asyncio.sleep(ERROR_SLEEP_S)
