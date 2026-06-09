"""Background worker: drive CFScraper against the TrackingState.

Walks each tracked series in insertion order, scrapes a missing chapter list
or downloads one missing chapter (oldest first) per iteration, then loops.
"""

import asyncio
import logging
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from .scraper import CFScraper
from .pattern_finder import ChapterListCache
from .series_index import SeriesIndex
from .tracking import TrackingState

logger = logging.getLogger(__name__)

IDLE_SLEEP_S = 60
ERROR_SLEEP_S = 30
# Chapter-to-chapter cooldown, jittered. Periodic timing is a Cloudflare
# anti-bot signal; humans don't read with metronome regularity.
WORK_SLEEP_MIN_S = 12
WORK_SLEEP_MAX_S = 25
# Wipe the patchright profile proactively every N successful chapters. Long
# before this we'd see a sticky block (~100 chapters on this IP), so we cycle
# the cookie jar before that threshold.
CHAPTERS_PER_RESET = 75
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
                     is_complete: Callable[[str, str], bool],
                     series_index: SeriesIndex) -> bool:
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
            chapter_dir = downloads_dir / series_name / f"chapter_{ch_num}"
            page_count = await scraper.fetch_chapter_pages(ch['url'], chapter_dir)
            (chapter_dir / "completed").write_text(datetime.now().isoformat())
            series_index.update_chapter(series_name, f"chapter_{ch_num}", chapter_dir)
            logger.info("✅ %s ch %s: %d pages on disk", series_name, ch_num, page_count)
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
                     is_complete: Callable[[str, str], bool],
                     series_index: SeriesIndex):
    logger.info("🦅 ripraven worker: starting")
    consecutive_failures = 0
    chapters_since_reset = 0
    while True:
        try:
            free = _free_mb(downloads_dir)
            if free < MIN_FREE_DISK_MB:
                logger.warning("🦅 worker idle: only %d MB free (< %d MB threshold)", free, MIN_FREE_DISK_MB)
                await asyncio.sleep(IDLE_SLEEP_S)
                continue

            did_work = await _one_cycle(scraper, tracking, chapter_cache, downloads_dir, is_complete, series_index)
            consecutive_failures = 0
            if did_work:
                chapters_since_reset += 1
                if chapters_since_reset >= CHAPTERS_PER_RESET:
                    logger.info("🦅 worker: proactive profile rotation after %d chapters", chapters_since_reset)
                    try:
                        await scraper.reset()
                    except Exception:
                        logger.exception("proactive scraper.reset failed")
                    chapters_since_reset = 0
                await asyncio.sleep(random.uniform(WORK_SLEEP_MIN_S, WORK_SLEEP_MAX_S))
            else:
                await asyncio.sleep(IDLE_SLEEP_S)
        except asyncio.CancelledError:
            logger.info("🦅 ripraven worker: cancelled")
            raise
        except Exception:
            consecutive_failures += 1
            logger.exception("worker cycle error (%d consecutive)", consecutive_failures)
            if consecutive_failures >= RESET_AFTER_FAILURES:
                logger.warning("🦅 worker: wiping profile after %d failures", consecutive_failures)
                try:
                    await scraper.reset()
                except Exception:
                    logger.exception("scraper.reset failed")
                consecutive_failures = 0
                chapters_since_reset = 0
            await asyncio.sleep(ERROR_SLEEP_S)
