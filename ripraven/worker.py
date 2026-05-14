"""Background worker: drive CFScraper against the TrackingState.

Walks each tracked series in insertion order, scrapes a missing chapter list
or downloads one missing chapter (oldest first) per iteration, then loops.
"""

import asyncio
import logging
import shutil
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
# After this many consecutive failures we throw away the Chrome session so the
# next cycle launches a fresh one (covers Chrome crashes, dead pages, expired
# context). Re-solving the challenge from scratch is cheap compared to retrying
# against a wedged browser indefinitely.
RESET_AFTER_FAILURES = 3
# Stop downloading new chapters when free disk falls below this. The reader
# UI still works against what's already on disk; the worker just goes idle
# until space is freed.
MIN_FREE_DISK_MB = 500


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


def _free_mb(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free // (1024 * 1024)
    except Exception:
        return 1 << 30  # if we can't tell, don't block


async def run_worker(scraper: CFScraper,
                     tracking: TrackingState,
                     chapter_cache: ChapterListCache,
                     downloads_dir: Path,
                     is_complete: Callable[[str, str], bool]):
    logger.info("🦅 ripraven worker: starting")
    consecutive_failures = 0
    while True:
        try:
            free = _free_mb(downloads_dir)
            if free < MIN_FREE_DISK_MB:
                logger.warning("🦅 worker idle: only %d MB free (< %d MB threshold)", free, MIN_FREE_DISK_MB)
                await asyncio.sleep(IDLE_SLEEP_S)
                continue

            did_work = await _one_cycle(scraper, tracking, chapter_cache, downloads_dir, is_complete)
            consecutive_failures = 0
            await asyncio.sleep(WORK_SLEEP_S if did_work else IDLE_SLEEP_S)
        except asyncio.CancelledError:
            logger.info("🦅 ripraven worker: cancelled")
            raise
        except Exception:
            consecutive_failures += 1
            logger.exception("worker cycle error (%d consecutive)", consecutive_failures)
            if consecutive_failures >= RESET_AFTER_FAILURES:
                logger.warning("🦅 worker: resetting browser context after %d failures", consecutive_failures)
                try:
                    await scraper.close()
                except Exception:
                    logger.exception("scraper.close failed during reset")
                consecutive_failures = 0
            await asyncio.sleep(ERROR_SLEEP_S)
