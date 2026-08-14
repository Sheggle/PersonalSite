"""Background worker: drive RavenScraper against the TrackingState.

Walks each tracked series in insertion order and downloads one missing
chapter per series per pass (oldest first), so a freshly tracked series
starts filling immediately instead of queueing behind older backlogs.
"""

import asyncio
import logging
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from .scraper import RavenScraper
from .pattern_finder import ChapterListCache
from .series_index import SeriesIndex
from .tracking import TrackingState

logger = logging.getLogger(__name__)

IDLE_SLEEP_S = 60
ERROR_SLEEP_S = 30
# Chapter-to-chapter cooldown, jittered — politeness towards the source, not
# a technical requirement.
WORK_SLEEP_MIN_S = 2
WORK_SLEEP_MAX_S = 5
# Re-scrape a series' chapter list once it is this old, so new releases get
# picked up. Series pages list every chapter, so a refresh is one request.
CHAPTER_LIST_TTL_S = 6 * 3600
# Stop downloading new chapters when free disk falls below this. The reader
# UI still works against what's already on disk; the worker just goes idle
# until space is freed.
MIN_FREE_DISK_MB = 500


async def _one_series(scraper: RavenScraper,
                      info: dict,
                      chapter_cache: ChapterListCache,
                      downloads_dir: Path,
                      is_complete: Callable[[str, str], bool],
                      series_index: SeriesIndex) -> int:
    """Refresh one series' chapter list if due, then fetch at most one of its
    missing chapters. Returns the number of work items completed."""
    series_name = info['series_name']
    done = 0

    if chapter_cache.is_stale(series_name, CHAPTER_LIST_TTL_S):
        logger.info("📚 scraping chapter list for %s", series_name)
        new = await scraper.scrape_chapter_list(info['series_url'])
        chapter_cache.set_chapters(series_name, new, info['series_url'])
        logger.info("📚 cached %d chapters for %s", len(new), series_name)
        done += 1

    for ch in chapter_cache.get_chapters(series_name) or []:
        ch_num = str(ch['number'])
        if is_complete(series_name, ch_num):
            continue
        logger.info("📥 fetching %s ch %s", series_name, ch_num)
        chapter_dir = downloads_dir / series_name / f"chapter_{ch_num}"
        page_count = await scraper.fetch_chapter_pages(ch['url'], chapter_dir)
        (chapter_dir / "completed").write_text(datetime.now().isoformat())
        series_index.update_chapter(series_name, f"chapter_{ch_num}", chapter_dir)
        logger.info("✅ %s ch %s: %d pages on disk", series_name, ch_num, page_count)
        done += 1
        await asyncio.sleep(random.uniform(WORK_SLEEP_MIN_S, WORK_SLEEP_MAX_S))
        break

    return done


async def _one_cycle(scraper: RavenScraper,
                     tracking: TrackingState,
                     chapter_cache: ChapterListCache,
                     downloads_dir: Path,
                     is_complete: Callable[[str, str], bool],
                     series_index: SeriesIndex) -> int:
    """One pass over all tracked series. A series that fails (deleted upstream,
    a chapter whose pages won't load) is logged and skipped so it cannot stall
    the rest of the library."""
    done = 0
    for slug, info in tracking.list().items():
        try:
            done += await _one_series(
                scraper, info, chapter_cache, downloads_dir, is_complete, series_index,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("🦅 worker: series %s failed this pass", slug)
    return done


def _free_mb(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free // (1024 * 1024)
    except Exception:
        return 1 << 30  # if we can't tell, don't block


async def run_worker(scraper: RavenScraper,
                     tracking: TrackingState,
                     chapter_cache: ChapterListCache,
                     downloads_dir: Path,
                     is_complete: Callable[[str, str], bool],
                     series_index: SeriesIndex):
    logger.info("🦅 ripraven worker: starting")
    while True:
        try:
            free = _free_mb(downloads_dir)
            if free < MIN_FREE_DISK_MB:
                logger.warning("🦅 worker idle: only %d MB free (< %d MB threshold)", free, MIN_FREE_DISK_MB)
                await asyncio.sleep(IDLE_SLEEP_S)
                continue

            done = await _one_cycle(scraper, tracking, chapter_cache, downloads_dir, is_complete, series_index)
            if not done:
                await asyncio.sleep(IDLE_SLEEP_S)
        except asyncio.CancelledError:
            logger.info("🦅 ripraven worker: cancelled")
            raise
        except Exception:
            logger.exception("worker cycle error")
            await asyncio.sleep(ERROR_SLEEP_S)
