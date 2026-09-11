"""Background worker: drive RavenScraper against the TrackingState.

Each pass walks every tracked series, refreshes any chapter list that has gone
stale and downloads the oldest missing chapters. A few series progress at once
and each contributes several chapters per pass, so a freshly tracked series
fills in minutes rather than trickling one chapter per cycle. Total load on the
source stays bounded by the scraper's process-wide image semaphore.

A chapter whose pages will not download is shelved on disk and the pass moves
on to the chapters behind it, so one dead CDN node costs a chapter rather than
the series. A series that achieves nothing at all is put in backoff by
TrackingState, and its error surfaces through /api/ripraven/tracked.
"""

import asyncio
import json
import logging
import random
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List

from .scraper import RavenScraper, describe_exc
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
# Consecutive chapter failures that end a pass early. Two in a row means the
# problem is the source, not the chapter — a whole CDN node answering 522 does
# exactly this — and marching through the rest of the series only burns the
# image budget the healthy series need. They get shelved on the next pass.
MAX_CONSECUTIVE_CHAPTER_FAILURES = 2
# Re-scrape a series' chapter list once it is this old, so new releases get
# picked up. Series pages list every chapter, so a refresh is one request.
CHAPTER_LIST_TTL_S = 6 * 3600
# Stop downloading new chapters when free disk falls below this. The reader
# UI still works against what's already on disk; the worker just goes idle
# until space is freed.
MIN_FREE_DISK_MB = 500
# A chapter whose images will not load — a CDN node whose origin is down
# answers 522 for every page of it at once — is marked on disk and skipped, so
# the chapters behind it still download. Retried on a widening delay, because
# the node usually comes back; the marker is what stops one dead chapter from
# parking a whole series forever.
FAILURE_MARKER = "failed"
CHAPTER_RETRY_MIN_S = 30 * 60
CHAPTER_RETRY_MAX_S = 24 * 3600


def read_chapter_failure(chapter_dir: Path) -> dict:
    """`{attempts, at, error}` for a chapter that failed, `{}` for one that
    has not."""
    try:
        return json.loads((chapter_dir / FAILURE_MARKER).read_text())
    except Exception:
        return {}


def chapter_is_shelved(chapter_dir: Path) -> bool:
    """True while a failed chapter is still inside its retry delay."""
    f = read_chapter_failure(chapter_dir)
    if not f:
        return False
    delay = min(CHAPTER_RETRY_MIN_S * 2 ** max(f.get('attempts', 1) - 1, 0),
                CHAPTER_RETRY_MAX_S)
    return time.time() - f.get('at', 0) < delay


def _note_chapter_failure(chapter_dir: Path, error: str) -> int:
    attempts = read_chapter_failure(chapter_dir).get('attempts', 0) + 1
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / FAILURE_MARKER).write_text(json.dumps({
        'attempts': attempts,
        'at': time.time(),
        'error': error,
    }))
    return attempts


async def _one_series(scraper: RavenScraper,
                      info: dict,
                      chapter_cache: ChapterListCache,
                      downloads_dir: Path,
                      is_complete: Callable[[str, str], bool],
                      series_index: SeriesIndex) -> int:
    """Refresh one series' chapter list if due, then fetch up to
    CHAPTERS_PER_PASS of its missing chapters, oldest first. Returns the number
    of work items completed.

    A chapter that will not download is shelved and the pass moves on to the
    next one; only a pass that achieves nothing at all is reported as a series
    failure."""
    series_name = info['series_name']
    done = 0

    if chapter_cache.is_stale(series_name, CHAPTER_LIST_TTL_S):
        logger.info("📚 scraping chapter list for %s", series_name)
        new = await scraper.scrape_chapter_list(info['series_url'])
        chapter_cache.set_chapters(series_name, new, info['series_url'])
        logger.info("📚 cached %d chapters for %s", len(new), series_name)
        done += 1

    attempted = 0
    downloaded = 0
    in_a_row = 0
    stuck: List[str] = []
    for ch in chapter_cache.get_chapters(series_name) or []:
        if attempted >= CHAPTERS_PER_PASS:
            break
        ch_num = str(ch['number'])
        if is_complete(series_name, ch_num):
            continue
        chapter_dir = downloads_dir / series_name / f"chapter_{ch_num}"
        if chapter_is_shelved(chapter_dir):
            continue
        logger.info("📥 fetching %s ch %s", series_name, ch_num)
        # A failed chapter still spends one of the pass's slots, so a series
        # whose whole back catalogue is unreachable cannot spin through
        # hundreds of chapters in a single pass.
        attempted += 1
        try:
            page_count = await scraper.fetch_chapter_pages(ch['url'], chapter_dir)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            reason = describe_exc(e)
            attempts = _note_chapter_failure(chapter_dir, reason)
            logger.warning("🚧 %s ch %s shelved after %d attempt(s): %s",
                           series_name, ch_num, attempts, reason)
            stuck.append(f"ch {ch_num} — {reason}")
            in_a_row += 1
            if in_a_row >= MAX_CONSECUTIVE_CHAPTER_FAILURES:
                break
            continue
        (chapter_dir / "completed").write_text(datetime.now().isoformat())
        (chapter_dir / FAILURE_MARKER).unlink(missing_ok=True)
        series_index.update_chapter(series_name, f"chapter_{ch_num}", chapter_dir)
        logger.info("✅ %s ch %s: %d pages on disk", series_name, ch_num, page_count)
        done += 1
        downloaded += 1
        in_a_row = 0
        await asyncio.sleep(random.uniform(WORK_SLEEP_MIN_S, WORK_SLEEP_MAX_S))

    # Nothing downloaded and something refused to: the series is stuck, and the
    # home page has to say so rather than show it as quietly queued.
    if stuck and not downloaded:
        more = f" (+{len(stuck) - 1} more)" if len(stuck) > 1 else ""
        raise RuntimeError(stuck[0] + more)

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
