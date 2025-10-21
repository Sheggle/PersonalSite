#!/usr/bin/env python3
"""
RipRaven Web Comic Reader - FastAPI backend server
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def natural_sort_key(text: str) -> list:
    """
    Generate a sort key for natural/numerical sorting.
    Converts '1' -> [0, '1'], '10' -> [0, '10'], 'chapter-10' -> [0, 'chapter-', 10]
    """
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
    chapter_num: int
    chapter_name: str
    images: List[str]
    page_count: int
    is_complete: bool


class InfiniteChaptersResponse(BaseModel):
    series: str
    current_chapter: int
    chapters: List[InfiniteChapterData]
    total_pages: int
    download_status: Dict[str, str]  # {"chapter_2": "downloading", "chapter_3": "complete", etc.}

class ImportMangaRequest(BaseModel):
    url: str

class ImportMangaResponse(BaseModel):
    series: str
    chapter: int
    message: str


class DownloadStatus(BaseModel):
    chapter_num: int
    status: str  # "pending", "downloading", "complete", "error", "not_available"
    progress: int = 0  # 0-100
    message: str = ""


class RipRavenAPI:
    def __init__(self, downloads_dir: str | Path = "../data/ripraven/downloads"):
        self.downloads_dir = Path(downloads_dir)
        # Calculate recent_chapters.json path relative to downloads_dir
        self.recent_file = Path(downloads_dir).parent / "recent_chapters.json"

        # Track background download status
        self.download_status = {}  # {f"{series}_{chapter}": DownloadStatus}

        # Initialize downloader
        from .async_downloader import AsyncDownloader
        self.downloader = AsyncDownloader(downloads_dir)

        self.reader_template, self.home_template = self._load_templates()

        # Initialize FastAPI router
        self.router = APIRouter()

        # Setup routes
        self.setup_routes()

    def _load_templates(self) -> tuple[str, str]:
        """Load the RipRaven HTML shells from the templates directory."""
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

    def setup_routes(self):
        """Setup all API routes."""

        @self.router.get("/")
        async def read_root():
            """Basic info endpoint for the RipRaven API."""
            return {"service": "ripraven", "status": "ok"}

        @self.router.get("/static/{file_path:path}")
        async def serve_static_files(file_path: str):
            """Serve static CSS/JS files."""
            # Get the static directory path relative to this module
            static_dir = Path(__file__).parent / "static"
            file_full_path = static_dir / file_path

            # Security check: ensure the file is within the static directory
            try:
                file_full_path.resolve().relative_to(static_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="Access denied")

            if not file_full_path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            # Set appropriate content type
            content_type = "text/plain"
            if file_path.endswith('.css'):
                content_type = "text/css"
            elif file_path.endswith('.js'):
                content_type = "application/javascript"

            return FileResponse(file_full_path, media_type=content_type)

        @self.router.get("/series", response_model=List[SeriesInfo])
        async def get_series():
            """Get all available series and their chapters."""
            try:
                return self.scan_series()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/chapters/{series_name}", response_model=List[str])
        async def get_chapter_images(series_name: str, chapter_name: str):
            """Get all image URLs for a specific chapter."""
            try:
                return self.get_chapter_images(series_name, chapter_name)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Chapter not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/images/{series_name}/{chapter_name}")
        async def get_chapter_images_list(series_name: str, chapter_name: str):
            """Get list of images for a chapter."""
            try:
                images = self.get_chapter_images(series_name, chapter_name)
                return {"images": images, "total": len(images)}
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Chapter not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/recent", response_model=List[RecentChapter])
        async def get_recent_chapters():
            """Get recently read chapters."""
            return self.load_recent_chapters()

        @self.router.post("/recent")
        async def update_recent_chapter(recent: RecentChapter):
            """Update recently read chapter."""
            try:
                self.save_recent_chapter(recent)
                return {"status": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/import-manga", response_model=ImportMangaResponse)
        async def import_manga(request: ImportMangaRequest):
            """Import a new manga from a RavenScans URL."""
            logger.debug("📥 Import manga request: %s", request.url)

            try:
                # Extract manga information from the URL
                from .pattern_finder import PatternFinder
                finder = PatternFinder()

                # Extract pattern and metadata
                pattern_result = finder.find_pattern(request.url)
                if not pattern_result:
                    raise HTTPException(status_code=400, detail="Could not extract manga information from URL")

                series_name = pattern_result.get('series', 'Unknown_Series')
                chapter_num = pattern_result.get('chapter', 1)
                base_pattern = pattern_result.get('base_pattern')
                start_number = pattern_result.get('start_number', 0)

                if not base_pattern:
                    raise HTTPException(status_code=400, detail="Could not extract download pattern from URL")

                logger.debug(
                    "📥 Extracted: series=%s, chapter=%s, pattern=%s",
                    series_name,
                    chapter_num,
                    base_pattern,
                )

                # Clean up series name for folder structure
                series_clean = series_name.replace(' ', '_').replace('-', '_')

                # Create chapter info
                chapter_info = {
                    'series': series_clean,
                    'chapter': str(chapter_num)
                }

                # Start download in background on the running event loop
                asyncio.create_task(
                    self.download_imported_manga(
                        series_clean,
                        chapter_num,
                        base_pattern,
                        start_number,
                        chapter_info
                    )
                )

                return ImportMangaResponse(
                    series=series_clean,
                    chapter=chapter_num,
                    message=f"Import started for {series_name} Chapter {chapter_num}"
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.exception("❌ Import error")
                raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

        @self.router.get("/infinite-chapters/{series_name}/{current_chapter}", response_model=InfiniteChaptersResponse)
        async def get_infinite_chapters(series_name: str, current_chapter: int, background_tasks: BackgroundTasks):
            """Get multiple chapters for infinite scroll reading with auto-download."""
            logger.debug(
                "🔍 Starting infinite chapters request: series=%s, chapter=%d",
                series_name,
                current_chapter,
            )

            try:
                # Get the main chapter and up to 2 additional chapters
                chapters_data = []
                total_pages = 0
                download_status = {}

                logger.debug("🔍 Checking downloader availability...")
                if not hasattr(self, 'downloader'):
                    logger.error("❌ Downloader not initialized!")
                    raise HTTPException(status_code=500, detail="Downloader not initialized")

                logger.debug("🔍 Downloader available, checking chapters...")

                # Check which chapters are available (current + next 3)
                for i in range(2):  # chapters 0, 1 relative to starting
                    chapter_num = current_chapter + i
                    logger.debug("🔍 Checking chapter %d...", chapter_num)

                    try:
                        chapter_status = self.downloader.get_chapter_status(series_name, chapter_num)
                        logger.debug("🔍 Chapter %d status: %s", chapter_num, chapter_status)
                    except Exception as e:
                        logger.exception("❌ Error getting chapter status for %d", chapter_num)
                        download_status[f"chapter_{chapter_num}"] = "error"
                        continue

                    if chapter_status["exists"]:
                        # Get images for this chapter
                        try:
                            chapter_name = f"chapter_{chapter_num}"
                            logger.debug("🔍 Loading images for %s/%s...", series_name, chapter_name)
                            images = self.get_chapter_images(series_name, chapter_name)
                            logger.debug("🔍 Found %d images for chapter %d", len(images), chapter_num)

                            chapters_data.append(InfiniteChapterData(
                                chapter_num=chapter_num,
                                chapter_name=chapter_name,
                                images=images,
                                page_count=len(images),
                                is_complete=chapter_status["complete"]
                            ))

                            total_pages += len(images)
                            download_status[f"chapter_{chapter_num}"] = "complete" if chapter_status["complete"] else "incomplete"

                        except Exception as e:
                            logger.exception("❌ Error loading chapter %d", chapter_num)
                            download_status[f"chapter_{chapter_num}"] = "error"
                    else:
                        logger.debug("🔍 Chapter %d does not exist", chapter_num)
                        download_status[f"chapter_{chapter_num}"] = "not_available"

                logger.debug("🔍 Found %d chapters, checking if more downloads needed...", len(chapters_data))

                try:
                    # Pass the highest available chapter so downloads start from the right point
                    background_tasks.add_task(
                        self.trigger_background_download,
                        series_name,
                        current_chapter,
                    )
                    logger.debug(
                        "🔍 Background download task added for chapters beyond %s",
                        current_chapter,
                    )
                except Exception as e:
                    logger.exception("❌ Error adding background task")

                logger.debug("🔍 Creating response...")
                response = InfiniteChaptersResponse(
                    series=series_name,
                    current_chapter=current_chapter,
                    chapters=chapters_data,
                    total_pages=total_pages,
                    download_status=download_status
                )
                logger.debug(
                    "✅ Response created successfully with %d chapters",
                    len(chapters_data),
                )
                return response

            except HTTPException:
                raise
            except Exception as e:
                logger.exception("❌ Unexpected error in infinite chapters")
                raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

        @self.router.get("/download-status/{series_name}")
        async def get_download_status(series_name: str):
            """Get current download status for background downloads."""
            try:
                status_list = []
                for key, status in self.download_status.items():
                    if key.startswith(f"{series_name}_"):
                        status_list.append(status)

                return {"statuses": status_list}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/image/{series_name}/{chapter_name}/{image_name}")
        async def serve_image(series_name: str, chapter_name: str, image_name: str):
            """Serve individual comic images."""
            image_path = self.downloads_dir / series_name / chapter_name / image_name

            if not image_path.exists():
                raise HTTPException(status_code=404, detail="Image not found")

            return FileResponse(image_path)

        # Catch-all route for /{series_name}/{chapter_num} - must be last!
        @self.router.get("/{series_name}/{chapter_num}", response_class=HTMLResponse)
        async def read_chapter(series_name: str, chapter_num: int):
            """Serve the comic reader with a specific series and chapter pre-loaded."""
            return self.get_reader_html()

        # Static files are embedded in the HTML, no need for separate directory

    async def download_imported_manga(
        self,
        series_name: str,
        chapter_num: int,
        base_pattern: str,
        start_number: int,
        chapter_info: dict
    ):
        """Background task responsible for downloading an imported manga chapter."""
        try:
            logger.debug(
                "🔄 Starting background download for imported manga: %s Chapter %d",
                series_name,
                chapter_num,
            )

            # Ensure downloader exists and is fresh for the current loop
            if not hasattr(self, 'downloader'):
                from .async_downloader import AsyncDownloader
                self.downloader = AsyncDownloader(self.downloads_dir)

            try:
                start_num = int(start_number)
            except (TypeError, ValueError):
                start_num = 0

            downloaded_files = await self.downloader.find_all_images(base_pattern, start_num, chapter_info)

            if downloaded_files:
                logger.info(
                    "✅ Successfully imported %s Chapter %d: %d pages",
                    series_name,
                    chapter_num,
                    len(downloaded_files),
                )
            else:
                logger.warning(
                    "❌ No images found for %s Chapter %d",
                    series_name,
                    chapter_num,
                )

        except Exception:
            logger.exception("❌ Background download error for %s", series_name)

    def scan_series(self) -> List[SeriesInfo]:
        """Scan downloads directory for available series."""
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

                # Check if chapter is complete
                completion_marker = chapter_dir / "completed"
                is_complete = completion_marker.exists()

                # Count pages
                image_files = self.get_image_files(chapter_dir)
                page_count = len(image_files)

                # Get last modified time
                try:
                    last_modified = datetime.fromtimestamp(chapter_dir.stat().st_mtime).isoformat()
                except:
                    last_modified = datetime.now().isoformat()

                chapters.append(ChapterInfo(
                    name=chapter_dir.name,
                    is_complete=is_complete,
                    page_count=page_count,
                    last_modified=last_modified
                ))

            # Sort chapters naturally (1, 2, 3, ... 10, 11 instead of 1, 10, 11, 2)
            chapters.sort(key=lambda x: natural_sort_key(x.name))

            series_list.append(SeriesInfo(
                name=series_dir.name,
                chapters=chapters
            ))

        # Sort series by name
        series_list.sort(key=lambda x: x.name)
        return series_list

    def get_image_files(self, chapter_dir: Path) -> List[str]:
        """Get sorted list of image files in a chapter directory."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

        image_files = []
        for file_path in chapter_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                image_files.append(file_path.name)

        # Sort files naturally (page_001.jpg, page_002.jpg, etc.)
        image_files.sort()
        return image_files

    def get_chapter_images(self, series_name: str, chapter_name: str) -> List[str]:
        """Get list of image URLs for a chapter."""
        chapter_path = self.downloads_dir / series_name / chapter_name

        if not chapter_path.exists():
            raise FileNotFoundError(f"Chapter not found: {series_name}/{chapter_name}")

        image_files = self.get_image_files(chapter_path)

        # Create URLs for images - use relative paths to work when mounted
        image_urls = []
        for image_file in image_files:
            url = f"image/{series_name}/{chapter_name}/{image_file}"
            image_urls.append(url)

        return image_urls

    def load_recent_chapters(self) -> List[RecentChapter]:
        """Load recently read chapters from file, deduplicated per series."""
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

            # Sort by last_read (newest first) and deduplicate by series
            chapters.sort(key=lambda r: (r.last_read or ""), reverse=True)

            deduped = []
            seen_series = set()
            for chapter in chapters:
                if chapter.series not in seen_series:
                    deduped.append(chapter)
                    seen_series.add(chapter.series)

            return deduped[:10]
        except Exception:
            return []

    def save_recent_chapter(self, recent: RecentChapter):
        """Save a recently read chapter."""
        # Load existing recent chapters
        recent_chapters = self.load_recent_chapters()

        # Remove previous entries for this series to keep only the latest chapter
        recent_chapters = [r for r in recent_chapters if r.series != recent.series]

        # Add to front of list
        recent_chapters.insert(0, recent)

        # Resort by last_read to ensure newest first and enforce limit
        recent_chapters.sort(key=lambda r: (r.last_read or ""), reverse=True)
        recent_chapters = recent_chapters[:10]

        # Save to file
        try:
            with open(self.recent_file, 'w') as f:
                json.dump([r.model_dump() for r in recent_chapters], f, indent=2)
        except Exception as e:
            logger.error("Error saving recent chapters: %s", e)

    async def trigger_background_download(self, series_name: str, current_chapter: int):
        """Trigger background download of next chapters."""
        try:
            logger.info(
                "🔄 Starting background download for %s chapters %d-%d",
                series_name,
                current_chapter + 1,
                current_chapter + 3,
            )

            chapters: list[int] = []

            # Update download status
            for i in range(1, 4):  # chapters +1, +2, +3
                chapter_num = current_chapter + i
                key = f"{series_name}_{chapter_num}"

                # Check if already downloading or complete
                if key in self.download_status:
                    continue

                chapters.append(chapter_num)

                # Mark as downloading
                self.download_status[key] = DownloadStatus(
                    chapter_num=chapter_num,
                    status="downloading",
                    progress=0,
                    message="Starting download..."
                )

            # Download the chapters - pass max_available_chapter instead of current_chapter
            results = await self.downloader.auto_download_next_chapters(
                series_name, chapters,
            )

            # Update status based on results
            for chapter_num, success in results.items():
                key = f"{series_name}_{chapter_num}"
                if success:
                    self.download_status[key] = DownloadStatus(
                        chapter_num=chapter_num,
                        status="complete",
                        progress=100,
                        message="Download complete"
                    )
                else:
                    self.download_status[key] = DownloadStatus(
                        chapter_num=chapter_num,
                        status="not_available",
                        progress=0,
                        message="Chapter not available"
                    )

            logger.info("✅ Background download completed for %s", series_name)

        except Exception as e:
            logger.exception("❌ Background download error for %s", series_name)
            # Mark failed chapters
            for i in range(1, 4):
                chapter_num = current_chapter + i
                key = f"{series_name}_{chapter_num}"
                self.download_status[key] = DownloadStatus(
                    chapter_num=chapter_num,
                    status="error",
                    progress=0,
                    message=str(e)
                )

    def get_reader_html(self) -> str:
        """Return the cached RipRaven reader HTML shell."""
        return self.reader_template

    def get_home_html(self) -> str:
        """Return the cached RipRaven home HTML shell."""
        return self.home_template


def create_ripraven_router(downloads_dir: str | Path = "../data/ripraven/downloads") -> APIRouter:
    """Factory for integrating the RipRaven UI and API into another FastAPI application."""
    api = RipRavenAPI(downloads_dir=downloads_dir)
    setattr(api.router, "ripraven_api", api)
    return api.router
