#!/usr/bin/env python3
"""RipRaven Web Comic Reader — FastAPI backend.

Architecture note: ravenscans.org and its image CDNs are behind a Cloudflare
managed challenge that blocks every server-side fetch we've tried (requests,
curl_cffi impersonation, headless playwright/patchright/nodriver). All chapter
discovery and image fetching now run in the user's browser via the userscript
at GET /api/ripraven/static/ripraven.user.js. The server's job is reduced to:

  - registering tracked series (POST /track),
  - handing out work batches to the userscript (GET /queue),
  - accepting the userscript's uploads (chapter-list, chapter pages),
  - serving the reader UI against the resulting on-disk library.
"""

import json
import logging
import re
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .pattern_finder import ChapterListCache, parse_chapter_url
from .tracking import TrackingState

logger = logging.getLogger(__name__)


def natural_sort_key(text: str) -> list:
    """1, 2, 10 sort like that, not 1, 10, 2. Also handles 'chapter_1.1'."""
    def convert(part):
        return int(part) if part.isdigit() else part.lower()
    return [convert(c) for c in re.split(r'(\d+)', text)]


class ChapterInfo(BaseModel):
    name: str
    is_complete: bool
    page_count: int
    last_modified: str


class SeriesInfo(BaseModel):
    name: str
    chapters: List[ChapterInfo]


class RecentChapter(BaseModel):
    series: str
    chapter: str
    last_read: str
    page_position: int = 0


class InfiniteChapterData(BaseModel):
    chapter_num: str
    chapter_name: str
    images: List[str]
    page_count: int
    is_complete: bool


class InfiniteChaptersResponse(BaseModel):
    series: str
    current_chapter: str
    chapters: List[InfiniteChapterData]
    total_pages: int
    download_status: Dict[str, str]


class TrackRequest(BaseModel):
    url: str


class TrackResponse(BaseModel):
    series_slug: str
    series_name: str
    chapter_num: str
    message: str


class ChapterListItem(BaseModel):
    number: str
    url: str


class ChapterListUpload(BaseModel):
    series_name: str
    series_url: Optional[str] = None
    chapters: List[ChapterListItem]


class QueueRelease(BaseModel):
    claim_token: str


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
COMPLETION_MARKER = "completed"


class RipRavenAPI:
    def __init__(self, downloads_dir: str | Path = "../data/ripraven/downloads"):
        self.downloads_dir = Path(downloads_dir)
        data_dir = self.downloads_dir.parent
        self.recent_file = data_dir / "recent_chapters.json"

        self.chapter_cache = ChapterListCache(data_dir)
        self.tracking = TrackingState(data_dir)

        self.reader_template, self.home_template = self._load_templates()
        self.router = APIRouter()
        self.setup_routes()

    def _load_templates(self) -> tuple[str, str]:
        try:
            base = resources.files(__package__).joinpath("templates")
            reader_html = base.joinpath("ripraven_reader.html").read_text(encoding="utf-8")
            home_html = base.joinpath("ripraven_home.html").read_text(encoding="utf-8")
            return reader_html, home_html
        except FileNotFoundError as exc:
            logger.error("RipRaven template missing: %s", exc)
            raise RuntimeError("RipRaven template missing") from exc
        except OSError as exc:
            logger.error("Failed to read RipRaven template: %s", exc)
            raise RuntimeError("Unable to load RipRaven template") from exc

    # ----- chapter status -------------------------------------------------

    def _chapter_dir(self, series_name: str, chapter_num: str) -> Path:
        return self.downloads_dir / series_name / f"chapter_{chapter_num}"

    def _chapter_is_complete(self, series_name: str, chapter_num: str) -> bool:
        return (self._chapter_dir(series_name, chapter_num) / COMPLETION_MARKER).exists()

    def _chapter_status(self, series_name: str, chapter_num: str) -> dict:
        d = self._chapter_dir(series_name, chapter_num)
        if not d.exists():
            return {"exists": False, "complete": False, "page_count": 0}
        page_count = sum(
            1 for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )
        return {
            "exists": True,
            "complete": (d / COMPLETION_MARKER).exists(),
            "page_count": page_count,
        }

    # ----- routes ---------------------------------------------------------

    def setup_routes(self):
        @self.router.get("/")
        async def read_root():
            return {"service": "ripraven", "status": "ok"}

        @self.router.get("/static/{file_path:path}")
        async def serve_static_files(file_path: str):
            static_dir = Path(__file__).parent / "static"
            file_full_path = static_dir / file_path
            try:
                file_full_path.resolve().relative_to(static_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="Access denied")
            if not file_full_path.exists():
                raise HTTPException(status_code=404, detail="File not found")
            content_type = "text/plain"
            if file_path.endswith('.css'):
                content_type = "text/css"
            elif file_path.endswith('.user.js') or file_path.endswith('.js'):
                content_type = "application/javascript"
            response = FileResponse(file_full_path, media_type=content_type)
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response

        @self.router.get("/series", response_model=List[SeriesInfo])
        async def get_series():
            try:
                return self.scan_series()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/recent", response_model=List[RecentChapter])
        async def get_recent_chapters():
            return self.load_recent_chapters()

        @self.router.post("/recent")
        async def update_recent_chapter(recent: RecentChapter):
            try:
                self.save_recent_chapter(recent)
                return {"status": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/images/{series_name}/{chapter_name}")
        async def get_chapter_images_list(series_name: str, chapter_name: str):
            try:
                images = self.get_chapter_images(series_name, chapter_name)
                return {"images": images, "total": len(images)}
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Chapter not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # ---- tracking + queue -------------------------------------------

        @self.router.post("/track", response_model=TrackResponse)
        async def track(req: TrackRequest):
            parsed = parse_chapter_url(req.url)
            if not parsed:
                raise HTTPException(
                    status_code=400,
                    detail="URL must look like https://ravenscans.org/<series>-chapter-<n>/",
                )
            self.tracking.add(
                series_slug=parsed['series_slug'],
                series_name=parsed['series_name'],
                series_url=parsed['series_url'],
                source_url=req.url,
            )
            return TrackResponse(
                series_slug=parsed['series_slug'],
                series_name=parsed['series_name'],
                chapter_num=parsed['chapter_num'],
                message=(
                    f"Now tracking {parsed['series_name']}. "
                    "Open a ravenscans.org tab with the ripraven userscript installed "
                    "to start downloading."
                ),
            )

        @self.router.get("/tracked")
        async def get_tracked():
            return self.tracking.status(self.chapter_cache, self._chapter_is_complete)

        @self.router.delete("/tracked/{series_slug}")
        async def stop_tracking(series_slug: str):
            self.tracking.remove(series_slug)
            return {"status": "ok"}

        @self.router.get("/queue")
        async def get_queue(limit: int = 1):
            items = self.tracking.build_queue(
                self.chapter_cache,
                self._chapter_is_complete,
                limit=max(1, min(limit, 5)),
            )
            return {"items": items}

        @self.router.post("/queue/release")
        async def release_claim(body: QueueRelease):
            self.tracking.release(body.claim_token)
            return {"status": "ok"}

        @self.router.post("/series/{series_slug}/chapter-list")
        async def upload_chapter_list(series_slug: str, body: ChapterListUpload):
            if series_slug not in self.tracking.list():
                raise HTTPException(status_code=404, detail="Series not tracked")
            chapters = [ch.model_dump() for ch in body.chapters]
            if not chapters:
                raise HTTPException(status_code=400, detail="Empty chapter list")
            self.chapter_cache.set_chapters(
                body.series_name,
                chapters,
                body.series_url,
            )
            logger.info(
                "📚 Chapter list for %s: %d chapters (uploaded by userscript)",
                body.series_name,
                len(chapters),
            )
            return {"status": "ok", "count": len(chapters)}

        @self.router.post("/series/{series_slug}/chapters/{chapter_num}/pages")
        async def upload_chapter_pages(
            series_slug: str,
            chapter_num: str,
            claim_token: str = Form(""),
            pages: List[UploadFile] = File(...),
        ):
            tracked = self.tracking.list().get(series_slug)
            if not tracked:
                raise HTTPException(status_code=404, detail="Series not tracked")
            if not pages:
                raise HTTPException(status_code=400, detail="No pages uploaded")

            series_name = tracked['series_name']
            chapter_dir = self._chapter_dir(series_name, chapter_num)
            chapter_dir.mkdir(parents=True, exist_ok=True)

            saved = 0
            for idx, up in enumerate(pages):
                # Trust the userscript's naming if it gave us "<n>.<ext>"; otherwise
                # synthesize a zero-padded order from the upload index.
                name = (up.filename or "").strip().lstrip("/").split("/")[-1]
                if not name or not any(name.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    name = f"{idx:03d}.jpg"
                out_path = chapter_dir / name
                data = await up.read()
                if not data:
                    continue
                out_path.write_bytes(data)
                saved += 1

            (chapter_dir / COMPLETION_MARKER).write_text(datetime.now().isoformat())
            if claim_token:
                self.tracking.release(claim_token)

            logger.info(
                "📥 %s chapter %s: saved %d pages from userscript",
                series_name, chapter_num, saved,
            )
            return {"status": "ok", "saved": saved}

        # ---- reader ------------------------------------------------------

        @self.router.get(
            "/infinite-chapters/{series_name}/{current_chapter}",
            response_model=InfiniteChaptersResponse,
        )
        async def get_infinite_chapters(series_name: str, current_chapter: str):
            chapters_data: list[InfiniteChapterData] = []
            total_pages = 0
            download_status: dict[str, str] = {}

            chapters_to_load = self.get_next_local_chapters(series_name, current_chapter, count=2)
            for chapter_name in chapters_to_load:
                chapter_num = self.extract_chapter_num_from_name(chapter_name)
                status = self._chapter_status(series_name, chapter_num)
                if not status["exists"]:
                    download_status[chapter_name] = "not_available"
                    continue
                try:
                    images = self.get_chapter_images(series_name, chapter_name)
                except Exception:
                    logger.exception("❌ Error loading chapter %s", chapter_num)
                    download_status[chapter_name] = "error"
                    continue
                chapters_data.append(InfiniteChapterData(
                    chapter_num=chapter_num,
                    chapter_name=chapter_name,
                    images=images,
                    page_count=len(images),
                    is_complete=status["complete"],
                ))
                total_pages += len(images)
                download_status[chapter_name] = "complete" if status["complete"] else "incomplete"

            return InfiniteChaptersResponse(
                series=series_name,
                current_chapter=current_chapter,
                chapters=chapters_data,
                total_pages=total_pages,
                download_status=download_status,
            )

        @self.router.get("/image/{series_name}/{chapter_name}/{image_name}")
        async def serve_image(series_name: str, chapter_name: str, image_name: str):
            image_path = self.downloads_dir / series_name / chapter_name / image_name
            if not image_path.exists():
                raise HTTPException(status_code=404, detail="Image not found")
            return FileResponse(image_path)

        # Catch-all reader route — must be last.
        @self.router.get("/{series_name}/{chapter_num}", response_class=HTMLResponse)
        async def read_chapter(series_name: str, chapter_num: int):
            return self.get_reader_html()

    # ----- local filesystem helpers ---------------------------------------

    def scan_series(self) -> List[SeriesInfo]:
        if not self.downloads_dir.exists():
            return []

        series_list = []
        for series_dir in self.downloads_dir.iterdir():
            if not series_dir.is_dir():
                continue
            chapters = []
            for chapter_dir in series_dir.iterdir():
                if not chapter_dir.is_dir():
                    continue
                is_complete = (chapter_dir / COMPLETION_MARKER).exists()
                page_count = sum(
                    1 for f in chapter_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                )
                try:
                    last_modified = datetime.fromtimestamp(chapter_dir.stat().st_mtime).isoformat()
                except Exception:
                    last_modified = datetime.now().isoformat()
                chapters.append(ChapterInfo(
                    name=chapter_dir.name,
                    is_complete=is_complete,
                    page_count=page_count,
                    last_modified=last_modified,
                ))
            chapters.sort(key=lambda x: natural_sort_key(x.name))
            series_list.append(SeriesInfo(name=series_dir.name, chapters=chapters))

        series_list.sort(key=lambda x: x.name)
        return series_list

    def get_available_chapters(self, series_name: str) -> List[str]:
        series_dir = self.downloads_dir / series_name
        if not series_dir.exists():
            return []
        chapters = []
        for chapter_dir in series_dir.iterdir():
            if chapter_dir.is_dir() and chapter_dir.name.startswith('chapter_'):
                has_images = any(
                    f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                    for f in chapter_dir.iterdir()
                )
                if has_images:
                    chapters.append(chapter_dir.name)
        chapters.sort(key=natural_sort_key)
        return chapters

    def get_next_local_chapters(self, series_name: str, current_chapter: str, count: int = 2) -> List[str]:
        chapters = self.get_available_chapters(series_name)
        if not chapters:
            return []
        chapter_name = f"chapter_{current_chapter}"
        try:
            current_idx = chapters.index(chapter_name)
        except ValueError:
            for idx, ch in enumerate(chapters):
                if natural_sort_key(ch) >= natural_sort_key(chapter_name):
                    current_idx = idx
                    break
            else:
                return []
        return chapters[current_idx:current_idx + count]

    def extract_chapter_num_from_name(self, chapter_name: str) -> str:
        return chapter_name[len("chapter_"):] if chapter_name.startswith("chapter_") else chapter_name

    def get_image_files(self, chapter_dir: Path) -> List[str]:
        files = [
            p.name for p in chapter_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
        files.sort(key=natural_sort_key)
        return files

    def get_chapter_images(self, series_name: str, chapter_name: str) -> List[str]:
        chapter_path = self.downloads_dir / series_name / chapter_name
        if not chapter_path.exists():
            raise FileNotFoundError(f"Chapter not found: {series_name}/{chapter_name}")
        return [f"image/{series_name}/{chapter_name}/{f}" for f in self.get_image_files(chapter_path)]

    # ----- recents --------------------------------------------------------

    def load_recent_chapters(self) -> List[RecentChapter]:
        if not self.recent_file.exists():
            return []
        try:
            with open(self.recent_file, 'r') as f:
                data = json.load(f)
            chapters = []
            for item in data:
                try:
                    chapters.append(RecentChapter(**item))
                except Exception:
                    continue
            chapters.sort(key=lambda r: (r.last_read or ""), reverse=True)
            deduped, seen = [], set()
            for c in chapters:
                if c.series not in seen:
                    deduped.append(c)
                    seen.add(c.series)
            return deduped[:10]
        except Exception:
            return []

    def save_recent_chapter(self, recent: RecentChapter):
        recents = self.load_recent_chapters()
        recents = [r for r in recents if r.series != recent.series]
        recents.insert(0, recent)
        recents.sort(key=lambda r: (r.last_read or ""), reverse=True)
        recents = recents[:10]
        try:
            self.recent_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.recent_file, 'w') as f:
                json.dump([r.model_dump() for r in recents], f, indent=2)
        except Exception as e:
            logger.error("Error saving recent chapters: %s", e)

    # ----- templates ------------------------------------------------------

    def get_reader_html(self) -> str:
        return self.reader_template

    def get_home_html(self) -> str:
        return self.home_template


def create_ripraven_router(downloads_dir: str | Path = "../data/ripraven/downloads") -> APIRouter:
    api = RipRavenAPI(downloads_dir=downloads_dir)
    setattr(api.router, "ripraven_api", api)
    return api.router
