"""Background worker: drive RavenScraper against the TrackingState.

Each pass walks every tracked series, refreshes any chapter list that has gone
stale and downloads the oldest missing chapters. A few series progress at once
and each contributes several chapters per pass, so a freshly tracked series
fills in minutes rather than trickling one chapter per cycle. Total load on the
source stays bounded by the scraper's process-wide image semaphore.

A series that fails is put in backoff by TrackingState rather than retried on
the next pass, and its error surfaces through /api/ripraven/tracked.
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
# Chapter-to-chapter cooldown, jittered — politeness towards the source, not a
# technical requirement. Image concurrency is what actually bounds our load, so
# this stays small.
WORK_SLEEP_MIN_S = 0.2
WORK_SLEEP_MAX_S = 0.6
# Chapters to pull per series per pass. Higher means a new series finishes
# sooner; lower means several series advance more evenly.
CHAPTERS_PER_PASS = 8
# Series worked on at once.
SERIES_CONCURRENCY = 3
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
    """Refresh one series' chapter list if due, then fetch up to
    CHAPTERS_PER_PASS of its missing chapters, oldest first. Returns the number
    of work items completed."""
    series_name = info['series_name']
    done = 0

    if chapter_cache.is_stale(series_name, CHAPTER_LIST_TTL_S):
        logger.info("📚 scraping chapter list for %s", series_name)
        new = await scraper.scrape_chapter_list(info['series_url'])
        chapter_cache.set_chapters(series_name, new, info['series_url'])
        logger.info("📚 cached %d chapters for %s", len(new), series_name)
        done += 1

    fetched = 0
    for ch in chapter_cache.get_chapters(series_name) or []:
        if fetched >= CHAPTERS_PER_PASS:
            break
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
        fetched += 1
        await asyncio.sleep(random.uniform(WORK_SLEEP_MIN_S, WORK_SLEEP_MAX_S))

    return done


async def _one_cycle(scraper: RavenScraper,
                     tracking: TrackingState,
                     chapter_cache: ChapterListCache,
                     downloads_dir: Path,
                     is_complete: Callable[[str, str], bool],
                     series_index: SeriesIndex) -> int:
    """One pass over all tracked series, SERIES_CONCURRENCY at a time. A series
    that fails (deleted upstream, a chapter whose pages won't load) is recorded
    and backed off so it cannot stall — or spam — the rest of the library."""
    sem = asyncio.Semaphore(SERIES_CONCURRENCY)

    async def _guarded(slug: str, info: dict) -> int:
        if tracking.in_backoff(slug):
            return 0
        async with sem:
            try:
                n = await _one_series(
                    scraper, info, chapter_cache, downloads_dir, is_complete, series_index,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                delay, count = tracking.note_failure(slug, f"{type(e).__name__}: {e}")
                # Full traceback once; after that the message alone, or a
                # persistent failure buries the log.
                if count == 1:
                    logger.exception("🦅 worker: series %s failed", slug)
                else:
                    logger.warning("🦅 worker: series %s failed again (%s), retrying in %ds",
                                   slug, e, delay)
                return 0
            tracking.note_success(slug)
            return n

    results = await asyncio.gather(
        *(_guarded(slug, info) for slug, info in tracking.list().items())
    )
    return sum(results)


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
