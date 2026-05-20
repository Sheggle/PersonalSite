"""Persistent series/chapter index for the RipRaven home page.

The downloads tree (~9 GB, ~4k chapter dirs, ~40k files) is too expensive to
walk on every `/api/ripraven/series` request — a cold-cache scan blocks the
home page for many seconds on a memory-pressured VPS. This module keeps a
JSON-backed mirror of the metadata that `scan_series` needs and is updated
in place by `upload_chapter_pages`.

Schema (`data/ripraven/series_index.json`):
    {series_name: {chapter_name: {is_complete, page_count, last_modified}}}

The first run after the file is missing (or unreadable) does a one-time
`os.scandir`-based rebuild from disk and writes the file. Subsequent process
starts read the JSON directly. Manual edits to the downloads tree won't be
picked up until either the file is deleted or a chapter for the affected
series is re-uploaded.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
COMPLETION_MARKER = "completed"


class SeriesIndex:
    def __init__(self, data_dir: str | Path, downloads_dir: str | Path):
        self.path = Path(data_dir) / "series_index.json"
        self.downloads_dir = Path(downloads_dir)
        self._state: dict = self._load_or_build()

    # ----- public ---------------------------------------------------------

    def list_all(self) -> dict:
        return self._state

    def chapter_meta(self, series_name: str, chapter_name: str) -> Optional[dict]:
        return self._state.get(series_name, {}).get(chapter_name)

    def is_complete(self, series_name: str, chapter_num: str) -> bool:
        meta = self.chapter_meta(series_name, f"chapter_{chapter_num}")
        return bool(meta and meta.get("is_complete"))

    def update_chapter(self, series_name: str, chapter_name: str, chapter_path: Path):
        meta = self._scan_chapter(chapter_path)
        self._state.setdefault(series_name, {})[chapter_name] = meta
        self._save()

    def rebuild(self) -> dict:
        self._state = self._scan_downloads()
        self._save()
        return self._state

    # ----- internals ------------------------------------------------------

    def _load_or_build(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("⚠️ series_index unreadable (%s), rebuilding", e)
        state = self._scan_downloads()
        self._save_state(state)
        return state

    def _scan_downloads(self) -> dict:
        state: dict = {}
        if not self.downloads_dir.exists():
            return state
        with os.scandir(self.downloads_dir) as series_it:
            for series_entry in series_it:
                if not series_entry.is_dir():
                    continue
                chapters: dict = {}
                with os.scandir(series_entry.path) as chapter_it:
                    for chapter_entry in chapter_it:
                        if not chapter_entry.is_dir():
                            continue
                        chapters[chapter_entry.name] = self._scan_chapter(
                            Path(chapter_entry.path)
                        )
                state[series_entry.name] = chapters
        return state

    @staticmethod
    def _scan_chapter(chapter_path: Path) -> dict:
        page_count = 0
        is_complete = False
        with os.scandir(chapter_path) as it:
            for entry in it:
                name = entry.name
                if name == COMPLETION_MARKER:
                    is_complete = True
                    continue
                # `entry.is_file()` uses d_type from getdents; no extra stat.
                if not entry.is_file():
                    continue
                dot = name.rfind('.')
                if dot == -1:
                    continue
                if name[dot:].lower() in IMAGE_EXTENSIONS:
                    page_count += 1
        try:
            last_modified = datetime.fromtimestamp(
                chapter_path.stat().st_mtime
            ).isoformat()
        except Exception:
            last_modified = datetime.now().isoformat()
        return {
            "is_complete": is_complete,
            "page_count": page_count,
            "last_modified": last_modified,
        }

    def _save(self):
        self._save_state(self._state)

    def _save_state(self, state: dict):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            with open(tmp, "w") as f:
                json.dump(state, f)
            tmp.replace(self.path)
        except Exception as e:
            logger.warning("⚠️ Could not save series_index: %s", e)
