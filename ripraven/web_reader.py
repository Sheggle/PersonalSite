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
    chapter_num: str  # String to support fractional chapters (1.1, 1.2, etc.)
    chapter_name: str
    images: List[str]
    page_count: int
    is_complete: bool


class InfiniteChaptersResponse(BaseModel):
    series: str
    current_chapter: str  # String to support fractional chapters
    chapters: List[InfiniteChapterData]
    total_pages: int
    download_status: Dict[str, str]  # {"chapter_1.1": "downloading", "chapter_2": "complete", etc.}

class ImportMangaRequest(BaseModel):
    url: str

class ImportMangaResponse(BaseModel):
    series: str
    chapter: str  # String to support fractional chapters
    message: str


class DownloadStatus(BaseModel):
    chapter_num: str  # String to support fractional chapters
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

        # Initialize chapter list cache for download lookahead
        from .pattern_finder import ChapterListCache
        cache_dir = Path(downloads_dir).parent
        self.chapter_cache = ChapterListCache(cache_dir)

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

            response = FileResponse(file_full_path, media_type=content_type)
            # Prevent aggressive browser caching of static files
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response

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
                chapter_num = str(pattern_result.get('chapter', '1'))  # Ensure string
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

                # Derive series URL for chapter list caching
                series_url = finder.get_series_url_from_chapter_url(request.url)

                # Create chapter info
                chapter_info = {
                    'series': series_clean,
                    'chapter': chapter_num
                }

                # Start download in background on the running event loop
                asyncio.create_task(
                    self.download_imported_manga(
                        series_clean,
                        chapter_num,
                        base_pattern,
                        start_number,
                        chapter_info,
                        series_url
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
        async def get_infinite_chapters(series_name: str, current_chapter: str, background_tasks: BackgroundTasks):
            """Get multiple chapters for infinite scroll reading with auto-download.

            Uses list-based navigation to handle fractional chapters (1.1, 1.2, etc.).
            """
            logger.debug(
                "🔍 Starting infinite chapters request: series=%s, chapter=%s",
                series_name,
                current_chapter,
            )

            try:
                chapters_data = []
                total_pages = 0
                download_status = {}

                logger.debug("🔍 Checking downloader availability...")
                if not hasattr(self, 'downloader'):
                    logger.error("❌ Downloader not initialized!")
                    raise HTTPException(status_code=500, detail="Downloader not initialized")

                logger.debug("🔍 Downloader available, getting available chapters...")

                # Use list-based navigation instead of incrementing
                chapters_to_load = self.get_next_local_chapters(series_name, current_chapter, count=2)
                logger.debug("🔍 Chapters to load: %s", chapters_to_load)

                for chapter_name in chapters_to_load:
                    chapter_num = self.extract_chapter_num_from_name(chapter_name)
                    logger.debug("🔍 Checking chapter %s...", chapter_num)

                    try:
                        chapter_status = self.downloader.get_chapter_status(series_name, chapter_num)
                        logger.debug("🔍 Chapter %s status: %s", chapter_num, chapter_status)
                    except Exception as e:
                        logger.exception("❌ Error getting chapter status for %s", chapter_num)
                        download_status[chapter_name] = "error"
                        continue

                    if chapter_status["exists"]:
                        try:
                            logger.debug("🔍 Loading images for %s/%s...", series_name, chapter_name)
                            images = self.get_chapter_images(series_name, chapter_name)
                            logger.debug("🔍 Found %d images for chapter %s", len(images), chapter_num)

                            chapters_data.append(InfiniteChapterData(
                                chapter_num=chapter_num,
                                chapter_name=chapter_name,
                                images=images,
                                page_count=len(images),
                                is_complete=chapter_status["complete"]
                            ))

                            total_pages += len(images)
                            download_status[chapter_name] = "complete" if chapter_status["complete"] else "incomplete"

                        except Exception as e:
                            logger.exception("❌ Error loading chapter %s", chapter_num)
                            download_status[chapter_name] = "error"
                    else:
                        logger.debug("🔍 Chapter %s does not exist", chapter_num)
                        download_status[chapter_name] = "not_available"

                logger.debug("🔍 Found %d chapters, checking if more downloads needed...", len(chapters_data))

                try:
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
        chapter_num: str,
        base_pattern: str,
        start_number: int,
        chapter_info: dict,
        series_url: str = None
    ):
        """Background task responsible for downloading an imported manga chapter.

        Also scrapes and caches the chapter list from Ravenscans for future lookahead.
        """
        try:
            logger.debug(
                "🔄 Starting background download for imported manga: %s Chapter %s",
                series_name,
                chapter_num,
            )

            # Ensure downloader exists and is fresh for the current loop
            if not hasattr(self, 'downloader'):
                from .async_downloader import AsyncDownloader
                self.downloader = AsyncDownloader(self.downloads_dir)

            # Cache the chapter list for this series if we have the series URL
            if series_url:
                logger.info("🔍 Caching chapter list from %s", series_url)
                self.chapter_cache.refresh_chapters(series_name, series_url)

            try:
                start_num = int(start_number)
            except (TypeError, ValueError):
                start_num = 0

            # Get next chapter from cache instead of incrementing
            next_chapters = self.chapter_cache.get_next_chapters(series_name, chapter_num, count=1)
            chapters_to_download = [chapter_num]
            if next_chapters:
                chapters_to_download.append(next_chapters[0])

            logger.debug("📥 Chapters to download: %s", chapters_to_download)

            # Build a template that can cover the requested chapter and the following one
            base_template = self._build_chapter_pattern_template(base_pattern, chapter_num)

            results = await self.downloader.download_chapters(
                series_name,
                chapters_to_download,
                base_pattern_template=base_template,
                series_info=chapter_info,
                start_number=start_num,
            )

            for ch_num in chapters_to_download:
                files = results.get(ch_num, [])
                if files:
                    logger.info(
                        "✅ Successfully imported %s Chapter %s: %d pages",
                        series_name,
                        ch_num,
                        len(files),
                    )
                else:
                    logger.warning(
                        "❌ No images found for %s Chapter %s",
                        series_name,
                        ch_num,
                    )

        except Exception:
            logger.exception("❌ Background download error for %s", series_name)

    def _build_chapter_pattern_template(self, base_pattern: str, chapter_num: str) -> str:
        """
        Build a reusable chapter pattern template with a {chapter} placeholder.
        Falls back to the original base pattern when no substitution is possible.

        Handles fractional chapters like 1.1 (URL: chapter-1-1).
        """
        stripped = base_pattern.rstrip('/')

        # For fractional chapters (e.g., "1.1"), look for pattern like chapter-1-1
        if '.' in str(chapter_num):
            chapter_url_form = str(chapter_num).replace('.', '-')
            # Look for the chapter pattern in the URL
            pattern = rf'(chapter-){re.escape(chapter_url_form)}(/?)$'
            match = re.search(pattern, stripped)
            if match:
                suffix = "/" if base_pattern.endswith("/") else ""
                template = stripped[:match.start()] + "chapter-{chapter}" + suffix
                logger.debug("🔧 Derived fractional chapter template: %s", template)
                return template

        # For integer chapters, look for trailing digits
        match = re.search(r'(\d+)$', stripped)

        if match:
            start, end = match.span(1)
            digits = stripped[start:end]

            try:
                # Compare as strings to handle both int and fractional
                if digits == str(chapter_num) or int(digits) == int(float(chapter_num)):
                    if digits.startswith('0') and len(digits) > 1:
                        placeholder = f"{{chapter:0{len(digits)}d}}"
                    else:
                        placeholder = "{chapter}"

                    suffix = "/" if base_pattern.endswith("/") else ""
                    template = f"{stripped[:start]}{placeholder}{stripped[end:]}{suffix}"
                    logger.debug("🔧 Derived chapter template: %s", template)
                    return template
            except ValueError:
                pass

        logger.debug("⚠️ Could not derive template from %s, using original pattern", base_pattern)
        return base_pattern

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

    def get_available_chapters(self, series_name: str) -> List[str]:
        """Get sorted list of available chapter names for a series.

        Returns chapter names like ['chapter_1', 'chapter_1.1', 'chapter_2', ...].
        """
        series_dir = self.downloads_dir / series_name
        if not series_dir.exists():
            return []

        chapters = []
        for chapter_dir in series_dir.iterdir():
            if chapter_dir.is_dir() and chapter_dir.name.startswith('chapter_'):
                chapters.append(chapter_dir.name)

        # Sort naturally to handle 1, 1.1, 1.2, 2, 10, etc.
        chapters.sort(key=natural_sort_key)
        return chapters

    def get_next_local_chapters(self, series_name: str, current_chapter: str, count: int = 2) -> List[str]:
        """Get the next N chapter names after the current chapter from local filesystem.

        Args:
            series_name: The series name
            current_chapter: Current chapter number (e.g., '1', '1.1', '2')
            count: Number of chapters to return (including current)

        Returns:
            List of chapter names starting from current chapter
        """
        chapters = self.get_available_chapters(series_name)
        if not chapters:
            return []

        # Convert chapter number to chapter name format
        chapter_name = f"chapter_{current_chapter}"

        try:
            current_idx = chapters.index(chapter_name)
        except ValueError:
            # Current chapter not found, try to find the first chapter >= current
            logger.warning("⚠️ Chapter %s not found locally, looking for closest match", chapter_name)
            for idx, ch in enumerate(chapters):
                if natural_sort_key(ch) >= natural_sort_key(chapter_name):
                    current_idx = idx
                    break
            else:
                return []

        # Return current chapter plus next chapters
        return chapters[current_idx:current_idx + count]

    def extract_chapter_num_from_name(self, chapter_name: str) -> str:
        """Extract chapter number from chapter name.

        E.g., 'chapter_1.1' -> '1.1', 'chapter_10' -> '10'
        """
        if chapter_name.startswith('chapter_'):
            return chapter_name[8:]  # len('chapter_') == 8
        return chapter_name

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

    async def trigger_background_download(self, series_name: str, current_chapter: str):
        """Trigger background download of next chapters using chapter cache.

        Uses the cached chapter list from Ravenscans to determine which chapters
        to download next, handling fractional chapters (1.1, 1.2, etc.) correctly.
        """
        try:
            # Check if we need to refresh the chapter cache
            if self.chapter_cache.needs_refresh(series_name, current_chapter, lookahead=3):
                logger.info("🔄 Chapter cache needs refresh for %s", series_name)
                series_url = self.chapter_cache.get_series_url(series_name)
                if series_url:
                    self.chapter_cache.refresh_chapters(series_name, series_url)

            # Get next chapters from cache
            next_chapters = self.chapter_cache.get_next_chapters(series_name, current_chapter, count=3)

            if not next_chapters:
                # Fallback: try to find next chapters locally (already downloaded)
                local_chapters = self.get_next_local_chapters(series_name, current_chapter, count=4)
                # Skip the first one (current chapter) and take the next 3
                next_chapters = [self.extract_chapter_num_from_name(ch) for ch in local_chapters[1:4]]

            if not next_chapters:
                logger.info("ℹ️ No next chapters found for %s after chapter %s", series_name, current_chapter)
                return

            logger.info(
                "🔄 Starting background download for %s chapters: %s",
                series_name,
                ", ".join(next_chapters),
            )

            chapters_to_download: list[str] = []

            # Update download status
            for chapter_num in next_chapters:
                key = f"{series_name}_{chapter_num}"

                # Check if already downloading or complete (allow retry for "not_available" or "error")
                existing_status = self.download_status.get(key)
                if existing_status and existing_status.status in ("downloading", "complete"):
                    continue

                # Check if already downloaded locally
                chapter_status = self.downloader.get_chapter_status(series_name, chapter_num)
                if chapter_status["exists"] and chapter_status["complete"]:
                    continue

                chapters_to_download.append(chapter_num)

                # Mark as downloading
                self.download_status[key] = DownloadStatus(
                    chapter_num=chapter_num,
                    status="downloading",
                    progress=0,
                    message="Starting download..."
                )

            if not chapters_to_download:
                logger.info("ℹ️ No new chapters to queue for %s", series_name)
                return

            # Get the chapter URL from cache and extract the download pattern
            base_pattern_template = None
            for chapter_num in chapters_to_download:
                chapter_url = self.chapter_cache.get_chapter_url(series_name, chapter_num)
                if chapter_url:
                    from .pattern_finder import PatternFinder
                    finder = PatternFinder()
                    pattern_result = finder.find_pattern(chapter_url)
                    if pattern_result and pattern_result.get('base_pattern'):
                        # Build template from the pattern
                        base_pattern = pattern_result['base_pattern']
                        base_pattern_template = self._build_chapter_pattern_template(
                            base_pattern, chapter_num
                        )
                        logger.info("🔗 Using pattern template: %s", base_pattern_template)
                        break

            # Download the chapters
            results = await self.downloader.download_chapters(
                series_name,
                chapters_to_download,
                base_pattern_template=base_pattern_template
            )

            # Update status based on results
            for chapter_num, files in results.items():
                key = f"{series_name}_{chapter_num}"
                if files:
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
            for chapter_num in next_chapters if 'next_chapters' in dir() else []:
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
