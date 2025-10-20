#!/usr/bin/env python3
"""
RipRaven Web Comic Reader - FastAPI backend server
"""

import asyncio
import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from logging_utils import get_logger

logger = get_logger(__name__)


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
    starting_chapter: int
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


class ComicWebServer:
    def __init__(self, downloads_dir: str = "../data/ripraven/downloads", port: int = 8000):
        self.downloads_dir = Path(downloads_dir)
        self.port = port
        # Calculate recent_chapters.json path relative to downloads_dir
        if isinstance(downloads_dir, str):
            downloads_path = Path(downloads_dir)
        else:
            downloads_path = downloads_dir
        self.recent_file = downloads_path.parent / "recent_chapters.json"

        # Track background download status
        self.download_status = {}  # {f"{series}_{chapter}": DownloadStatus}

        # Initialize downloader
        from async_downloader import AsyncDownloader
        self.downloader = AsyncDownloader(downloads_dir)

        # Initialize FastAPI app
        self.app = FastAPI(
            title="RipRaven Comic Reader",
            description="Web-based comic reader for downloaded manga",
            version="2.0.0"
        )

        # Setup routes
        self.setup_routes()

    def setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def read_root():
            """Serve the main comic reader interface."""
            return self.get_index_html()

        @self.app.get("/api/series", response_model=List[SeriesInfo])
        async def get_series():
            """Get all available series and their chapters."""
            try:
                return self.scan_series()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/chapters/{series_name}", response_model=List[str])
        async def get_chapter_images(series_name: str, chapter_name: str):
            """Get all image URLs for a specific chapter."""
            try:
                return self.get_chapter_images(series_name, chapter_name)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Chapter not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/images/{series_name}/{chapter_name}")
        async def get_chapter_images_list(series_name: str, chapter_name: str):
            """Get list of images for a chapter."""
            try:
                images = self.get_chapter_images(series_name, chapter_name)
                return {"images": images, "total": len(images)}
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Chapter not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/recent", response_model=List[RecentChapter])
        async def get_recent_chapters():
            """Get recently read chapters."""
            return self.load_recent_chapters()

        @self.app.post("/api/recent")
        async def update_recent_chapter(recent: RecentChapter):
            """Update recently read chapter."""
            try:
                self.save_recent_chapter(recent)
                return {"status": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/import-manga", response_model=ImportMangaResponse)
        async def import_manga(request: ImportMangaRequest):
            """Import a new manga from a RavenScans URL."""
            logger.debug("📥 Import manga request: %s", request.url)

            try:
                # Extract manga information from the URL
                from pattern_finder import PatternFinder
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

        @self.app.get("/api/infinite-chapters/{series_name}/{starting_chapter}", response_model=InfiniteChaptersResponse)
        async def get_infinite_chapters(series_name: str, starting_chapter: int, background_tasks: BackgroundTasks):
            """Get multiple chapters for infinite scroll reading with auto-download."""
            logger.debug(
                "🔍 Starting infinite chapters request: series=%s, chapter=%d",
                series_name,
                starting_chapter,
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
                for i in range(4):  # chapters 0, 1, 2, 3 relative to starting
                    chapter_num = starting_chapter + i
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

                # Sliding window logic: Always ensure we have 3 chapters ahead of the highest available
                # Find the highest chapter number we have
                max_available_chapter = max([ch.chapter_num for ch in chapters_data]) if chapters_data else starting_chapter - 1

                # Calculate what chapters we should have (starting_chapter + next 6 for wider buffer)
                target_chapters = list(range(starting_chapter, starting_chapter + 7))
                missing_chapters = []

                for target_chapter in target_chapters:
                    chapter_exists = any(ch.chapter_num == target_chapter for ch in chapters_data)
                    if not chapter_exists:
                        missing_chapters.append(target_chapter)

                logger.debug("🔍 Max available chapter: %s", max_available_chapter)
                logger.debug("🔍 Target chapters: %s", target_chapters)
                logger.debug("🔍 Missing chapters: %s", missing_chapters)

                # Always trigger background download if we have missing chapters
                if missing_chapters:
                    try:
                        # Pass the highest available chapter so downloads start from the right point
                        background_tasks.add_task(
                            self.trigger_background_download,
                            series_name,
                            max_available_chapter
                        )
                        logger.debug(
                            "🔍 Background download task added for chapters beyond %s",
                            max_available_chapter,
                        )
                    except Exception as e:
                        logger.exception("❌ Error adding background task")
                else:
                    logger.debug("🔍 No missing chapters, no download needed")

                logger.debug("🔍 Creating response...")
                response = InfiniteChaptersResponse(
                    series=series_name,
                    starting_chapter=starting_chapter,
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

        @self.app.get("/api/download-status/{series_name}")
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

        @self.app.get("/image/{series_name}/{chapter_name}/{image_name}")
        async def serve_image(series_name: str, chapter_name: str, image_name: str):
            """Serve individual comic images."""
            image_path = self.downloads_dir / series_name / chapter_name / image_name

            if not image_path.exists():
                raise HTTPException(status_code=404, detail="Image not found")

            return FileResponse(image_path)

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
                from async_downloader import AsyncDownloader
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

        except Exception as e:
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

            # Sort chapters
            chapters.sort(key=lambda x: x.name)

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

        # Create URLs for images - use relative paths to work with mounting
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
                json.dump([r.dict() for r in recent_chapters], f, indent=2)
        except Exception as e:
            logger.error("Error saving recent chapters: %s", e)

    async def trigger_background_download(self, series_name: str, starting_chapter: int):
        """Trigger background download of next chapters."""
        try:
            logger.info(
                "🔄 Starting background download for %s chapters %d-%d",
                series_name,
                starting_chapter + 1,
                starting_chapter + 3,
            )

            # Update download status
            for i in range(1, 4):  # chapters +1, +2, +3
                chapter_num = starting_chapter + i
                key = f"{series_name}_{chapter_num}"

                # Check if already downloading or complete
                if key in self.download_status:
                    continue

                # Mark as downloading
                self.download_status[key] = DownloadStatus(
                    chapter_num=chapter_num,
                    status="downloading",
                    progress=0,
                    message="Starting download..."
                )

            # Download the chapters - pass max_available_chapter instead of starting_chapter
            results = await self.downloader.auto_download_next_chapters(
                series_name, starting_chapter, ahead_count=3
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
                chapter_num = starting_chapter + i
                key = f"{series_name}_{chapter_num}"
                self.download_status[key] = DownloadStatus(
                    chapter_num=chapter_num,
                    status="error",
                    progress=0,
                    message=str(e)
                )

    def get_index_html(self) -> str:
        """Generate the main HTML page."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 RipRaven Comic Reader</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a1a;
            color: #ffffff;
            line-height: 1.6;
        }

        .header {
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            flex-wrap: wrap;
            background: #2d2d2d;
            padding: 1rem;
            position: sticky;
            top: 0;
            z-index: 100;
            border-bottom: 2px solid #ff6b35;
            box-shadow: 0 2px 10px rgba(0,0,0,0.5);
        }

        .header-content {
            flex: 1 1 0%;
        }

        .header.collapsed {
            padding: 0.75rem 1rem;
        }

        .header.collapsed .header-content {
            display: none;
        }

        .header-toggle {
            background: #ff6b35;
            color: #ffffff;
            border: none;
            padding: 0.5rem 0.75rem;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
            min-width: 120px;
            transition: background-color 0.2s ease;
        }

        .header-toggle:hover {
            background: #e55a2b;
        }

        .header h1 {
            color: #ff6b35;
            margin-bottom: 1rem;
            font-size: 1.5rem;
        }

        .controls {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            align-items: center;
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .control-group label {
            color: #cccccc;
            font-weight: 500;
        }

        select {
            background: #3d3d3d;
            color: #ffffff;
            border: 1px solid #555;
            padding: 0.5rem;
            border-radius: 4px;
            min-width: 150px;
        }

        select:focus {
            outline: none;
            border-color: #ff6b35;
        }

        .status {
            background: #333;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            color: #aaa;
            font-size: 0.9rem;
        }

        .recent-section {
            background: #2a2a2a;
            margin: 1rem;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #ff6b35;
        }

        .recent-title {
            color: #ff6b35;
            margin-bottom: 0.5rem;
            font-weight: bold;
        }

        .recent-list {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }

        .recent-item {
            background: #3d3d3d;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 1px solid #555;
        }

        .recent-item:hover {
            background: #4d4d4d;
            border-color: #ff6b35;
            transform: translateY(-2px);
        }

        .comic-container {
            max-width: 1000px;
            margin: 2rem auto;
            padding: 0 1rem;
        }

        .comic-page {
            margin: 0;
            padding: 0;
            text-align: center;
            line-height: 0;
        }

        .comic-page img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }

        /* Floating Chapter Indicator */
        .chapter-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(45, 45, 45, 0.95);
            color: #ff6b35;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-weight: bold;
            font-size: 1rem;
            border: 2px solid #ff6b35;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            z-index: 1000;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }

        .chapter-indicator.hidden {
            opacity: 0;
            transform: translateX(100px);
        }

        /* Chapter Divider */
        .chapter-divider {
            margin: 2rem 0;
            text-align: center;
            position: relative;
        }

        .chapter-divider::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(to right, transparent, #ff6b35, transparent);
        }

        .chapter-divider-text {
            background: #1a1a1a;
            color: #ff6b35;
            padding: 0.5rem 1.5rem;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
            border: 1px solid #ff6b35;
            display: inline-block;
            position: relative;
            z-index: 1;
        }

        /* Download Status Indicator */
        .download-status {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(45, 45, 45, 0.95);
            color: #ffffff;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-size: 0.9rem;
            border: 1px solid #555;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            z-index: 1000;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
            max-width: 300px;
        }

        .download-status.hidden {
            opacity: 0;
            transform: translateY(100px);
        }

        .download-progress {
            margin-top: 0.5rem;
        }

        .progress-bar {
            background: #333;
            border-radius: 10px;
            height: 6px;
            overflow: hidden;
        }

        .progress-fill {
            background: #ff6b35;
            height: 100%;
            transition: width 0.3s ease;
        }

        .loading {
            text-align: center;
            padding: 2rem;
            color: #aaa;
        }

        .error {
            text-align: center;
            padding: 2rem;
            color: #ff6b6b;
            background: #2d1f1f;
            border-radius: 8px;
            margin: 1rem;
        }

        .empty-state {
            text-align: center;
            padding: 3rem;
            color: #aaa;
        }

        .empty-state h2 {
            color: #ff6b35;
            margin-bottom: 1rem;
        }

        @media (max-width: 768px) {
            /* Mobile layout for controls */
            .controls {
                flex-direction: column;
                align-items: stretch;
                gap: 0.75rem;
            }

            .control-group {
                flex-direction: column;
                align-items: stretch;
                gap: 0.5rem;
            }

            select {
                min-width: unset;
                width: 100%;
                padding: 0.75rem;
                font-size: 1rem;
            }

            /* Optimize header for mobile */
            .header {
                padding: 0.75rem;
                gap: 0.75rem;
            }

            .header h1 {
                font-size: 1.3rem;
                margin-bottom: 0.75rem;
            }

            .header-toggle {
                padding: 0.6rem 0.8rem;
                font-size: 0.9rem;
                min-width: 100px;
            }

            /* Mobile-friendly comic container */
            .comic-container {
                margin: 1rem auto;
                padding: 0 0.5rem;
            }

            /* Improve comic page display on mobile */
            .comic-page img {
                max-width: 100%;
                height: auto;
                border-radius: 4px;
            }

            /* Mobile chapter indicator */
            .chapter-indicator {
                font-size: 1rem;
                padding: 0.6rem 1rem;
                border-radius: 6px;
                top: 10px;
                right: 10px;
                /* Ensure it doesn't interfere with mobile browser UI */
                z-index: 200;
            }

            /* Optimize import section for mobile */
            .import-section {
                padding: 0.75rem;
                margin-top: 0.75rem;
            }

            .import-section input[type="url"] {
                padding: 0.75rem;
                font-size: 1rem;
                border-radius: 6px;
            }

            .import-section button {
                padding: 0.75rem 1rem;
                font-size: 1rem;
                border-radius: 6px;
            }

            /* Mobile navigation improvements */
            button, input[type="button"] {
                min-height: 44px; /* Touch-friendly size */
                font-size: 1rem;
            }

            /* Download status on mobile */
            .download-status {
                max-width: 90%;
                margin: 0.5rem;
                font-size: 0.9rem;
            }
        }

        @media (max-width: 480px) {
            /* Extra small screens */
            .header {
                padding: 0.5rem;
            }

            .header h1 {
                font-size: 1.1rem;
                margin-bottom: 0.5rem;
            }

            .header-toggle {
                padding: 0.5rem 0.7rem;
                font-size: 0.85rem;
                min-width: 80px;
            }

            .comic-container {
                margin: 0.5rem auto;
                padding: 0 0.25rem;
            }

            .chapter-indicator {
                font-size: 0.9rem;
                padding: 0.5rem 0.8rem;
                top: 8px;
                right: 8px;
            }

            /* Compact controls for very small screens */
            .controls {
                gap: 0.5rem;
            }

            .control-group {
                gap: 0.3rem;
            }

            select, input {
                padding: 0.6rem;
                font-size: 0.9rem;
            }

            /* Chapter dividers on mobile */
            .chapter-divider {
                margin: 1rem 0 0.5rem;
                font-size: 1rem;
            }

            .import-section {
                padding: 0.5rem;
                margin-top: 0.5rem;
            }
        }

        @media (max-width: 320px) {
            /* Very small screens */
            .header h1 {
                font-size: 1rem;
            }

            .header-toggle {
                font-size: 0.8rem;
                padding: 0.4rem 0.6rem;
                min-width: 70px;
            }

            .chapter-indicator {
                font-size: 0.8rem;
                padding: 0.4rem 0.6rem;
                top: 5px;
                right: 5px;
            }

            select, input {
                padding: 0.5rem;
                font-size: 0.85rem;
            }
        }

        /* Smooth scrolling */
        html {
            scroll-behavior: smooth;
        }

        /* Loading animation */
        .spinner {
            border: 2px solid #333;
            border-top: 2px solid #ff6b35;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Import Form Styles */
        .import-section {
            background: #333333;
            border: 1px solid #555;
            border-radius: 6px;
            padding: 1rem;
            margin-top: 1rem;
        }

        .import-form {
            display: flex;
            gap: 0.5rem;
            align-items: center;
            flex-wrap: wrap;
        }

        input[type="url"] {
            flex: 1;
            background: #3d3d3d;
            color: #ffffff;
            border: 1px solid #555;
            padding: 0.5rem;
            border-radius: 4px;
            min-width: 300px;
        }

        input[type="url"]:focus {
            outline: none;
            border-color: #ff6b35;
        }

        input[type="url"]::placeholder {
            color: #888;
        }

        button {
            background: #ff6b35;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
            transition: background-color 0.2s;
        }

        button:hover {
            background: #e55a2b;
        }

        button:disabled {
            background: #666;
            cursor: not-allowed;
        }

        .import-status {
            color: #cccccc;
            font-style: italic;
            margin-top: 0.5rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <button
            class="header-toggle"
            id="headerToggle"
            type="button"
            aria-expanded="true"
            aria-controls="headerContent"
        >
            Hide Header
        </button>
        <div class="header-content" id="headerContent">
            <h1>🔥 RipRaven Comic Reader</h1>
            <div class="controls">
                <div class="control-group">
                    <label for="seriesSelect">Series:</label>
                    <select id="seriesSelect">
                        <option value="">Loading...</option>
                    </select>
                </div>
                <div class="control-group">
                    <label for="chapterSelect">Chapter:</label>
                    <select id="chapterSelect" disabled>
                        <option value="">Select series first</option>
                    </select>
                </div>
                <div class="status" id="status">
                    Loading series...
                </div>
            </div>

            <!-- Import New Manga Section -->
            <div class="import-section">
                <h3>📥 Import New Manga</h3>
                <div class="import-form">
                    <input
                        type="url"
                        id="mangaUrl"
                        placeholder="Paste RavenScans URL (e.g., https://ravenscans.com/manga-name-chapter-1/)"
                        value=""
                    />
                    <button id="importBtn" onclick="importManga()">Import</button>
                </div>
                <div class="import-status" id="importStatus"></div>
            </div>
        </div>
    </div>

    <div id="recentSection" class="recent-section" style="display: none;">
        <div class="recent-title">📖 Recently Read</div>
        <div class="recent-list" id="recentList"></div>
    </div>

    <!-- Floating Chapter Indicator -->
    <div id="chapterIndicator" class="chapter-indicator hidden">
        Chapter 1
    </div>

    <!-- Download Status Indicator -->
    <div id="downloadStatus" class="download-status hidden">
        <div id="downloadText">Downloading chapters...</div>
        <div class="download-progress">
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill" style="width: 0%"></div>
            </div>
        </div>
    </div>

    <div id="comicContainer" class="comic-container">
        <div class="empty-state">
            <h2>Welcome to RipRaven Comic Reader</h2>
            <p>Select a series and chapter from the dropdowns above to start reading.</p>
            <p>📚 Use the vertical scroll to read through pages continuously.</p>
            <p>🔄 Multiple chapters will load seamlessly for infinite reading!</p>
        </div>
    </div>

    <script>
        class ComicReader {
            constructor() {
                this.currentSeries = null;
                this.currentChapter = null;
                this.seriesData = [];
                this.recentChapters = [];
                this.chaptersData = [];  // Array of chapter data for infinite scroll
                this.chapterBoundaries = [];  // Array of {chapterNum, startY, endY}
                this.currentDisplayChapter = null;

                // API base URL - works both when standalone and when mounted
                const rawPath = window.location.pathname.replace(/\/$/, '');
                const mountMatch = rawPath.match(/^(.*?\/api\/ripraven)(?:\/.*)?$/);
                const basePath = mountMatch ? mountMatch[1] : '';
                this.apiBase = `${basePath}/api`.replace(/\/{2,}/g, '/');
                console.info('[RipRaven] API base resolved:', {
                    pathname: window.location.pathname,
                    rawPath,
                    basePath: this.apiBase
                });

                this.setupElements();
                this.loadSeries();
                this.loadRecent();
                this.setupKeyboardShortcuts();
                this.setupScrollTracking();
            }

            setupElements() {
                this.seriesSelect = document.getElementById('seriesSelect');
                this.chapterSelect = document.getElementById('chapterSelect');
                this.status = document.getElementById('status');
                this.comicContainer = document.getElementById('comicContainer');
                this.recentSection = document.getElementById('recentSection');
                this.recentList = document.getElementById('recentList');
                this.chapterIndicator = document.getElementById('chapterIndicator');
                this.downloadStatus = document.getElementById('downloadStatus');
                this.downloadText = document.getElementById('downloadText');
                this.progressFill = document.getElementById('progressFill');
                this.importSection = document.querySelector('.import-section');
                this.header = document.querySelector('.header');
                this.headerToggle = document.getElementById('headerToggle');
                this.headerContent = document.getElementById('headerContent');

                this.toggleImportSection(true);
                this.setHeaderCollapsed(false);

                this.seriesSelect.addEventListener('change', () => this.onSeriesChange());
                this.chapterSelect.addEventListener('change', () => this.onChapterChange());

                if (this.headerToggle) {
                    this.headerToggle.addEventListener('click', () => this.onHeaderToggle());
                }
            }

            toggleImportSection(visible) {
                if (!this.importSection) return;
                this.importSection.style.display = visible ? '' : 'none';
            }

            setHeaderCollapsed(collapsed) {
                if (!this.header || !this.headerToggle) return;
                this.header.classList.toggle('collapsed', collapsed);

                const label = collapsed ? 'Show Header' : 'Hide Header';
                this.headerToggle.textContent = label;
                this.headerToggle.setAttribute('aria-expanded', (!collapsed).toString());
            }

            onHeaderToggle() {
                if (!this.header) return;
                const shouldCollapse = !this.header.classList.contains('collapsed');
                this.setHeaderCollapsed(shouldCollapse);
            }

            setupScrollTracking() {
                // Track if we're in initial setup to prevent rapid updates
                this.isInitialSetup = false;

                // Use Intersection Observer for more accurate chapter detection
                this.chapterObserver = new IntersectionObserver((entries) => {
                    console.log('[INTERSECT] Intersection event fired with', entries.length, 'entries at', new Date().toISOString());
                    console.log('[INTERSECT] isInitialSetup:', this.isInitialSetup);

                    // During initial setup, ignore intersection events for a short period
                    if (this.isInitialSetup) {
                        console.log('[INTERSECT] Ignoring intersection events during initial setup');
                        return;
                    }

                    entries.forEach(entry => {
                        const chapterNum = parseInt(entry.target.dataset.chapterNum);
                        console.log('[INTERSECT] Processing entry:', {
                            chapterNum,
                            isIntersecting: entry.isIntersecting,
                            target: entry.target.className,
                            currentDisplayChapter: this.currentDisplayChapter
                        });

                        if (entry.isIntersecting) {
                            console.log('[INTERSECT] Chapter', chapterNum, 'is intersecting');
                            if (chapterNum && this.currentDisplayChapter !== chapterNum) {
                                console.log('[INTERSECT] Updating chapter indicator from', this.currentDisplayChapter, 'to', chapterNum);
                                this.currentDisplayChapter = chapterNum;
                                this.chapterIndicator.textContent = `Chapter ${chapterNum}`;
                                console.log('[INTERSECT] Chapter indicator now shows:', this.chapterIndicator.textContent);
                            } else if (chapterNum === this.currentDisplayChapter) {
                                console.log('[INTERSECT] Chapter', chapterNum, 'already current, no update needed');
                            } else {
                                console.log('[INTERSECT] Invalid chapter number:', chapterNum);
                            }
                        } else {
                            console.log('[INTERSECT] Chapter', chapterNum, 'is NOT intersecting');
                        }
                    });
                }, {
                    rootMargin: '-20% 0px -70% 0px', // Trigger when chapter is 20% down from top
                    threshold: 0
                });

                // Setup periodic polling for new content
                this.setupContentPolling();
            }

            async loadSeries() {
                try {
                    const response = await fetch(`${this.apiBase}/series`);
                    this.seriesData = await response.json();

                    this.seriesSelect.innerHTML = '<option value="">Select a series...</option>';

                    this.seriesData.forEach(series => {
                        const option = document.createElement('option');
                        option.value = series.name;
                        option.textContent = `${series.name} (${series.chapters.length} chapters)`;
                        this.seriesSelect.appendChild(option);
                    });

                    this.status.textContent = `Found ${this.seriesData.length} series`;
                } catch (error) {
                    this.status.textContent = 'Error loading series';
                    console.error('Error loading series:', error);
                }
            }

            async loadRecent() {
                try {
                    const response = await fetch(`${this.apiBase}/recent`);
                    this.recentChapters = await response.json();

                    if (this.recentChapters.length > 0) {
                        this.updateRecentSection();
                    }
                } catch (error) {
                    console.error('Error loading recent chapters:', error);
                }
            }

            updateRecentSection() {
                if (this.recentChapters.length === 0) {
                    this.recentSection.style.display = 'none';
                    return;
                }

                this.recentSection.style.display = 'block';
                this.recentList.innerHTML = '';

                this.recentChapters.forEach(recent => {
                    const item = document.createElement('div');
                    item.className = 'recent-item';
                    item.textContent = `${recent.series} - ${recent.chapter}`;
                    item.addEventListener('click', () => {
                        this.loadRecentChapter(recent.series, recent.chapter);
                    });
                    this.recentList.appendChild(item);
                });
            }

            loadRecentChapter(seriesName, chapterName) {
                // Set the series
                this.seriesSelect.value = seriesName;
                this.onSeriesChange();

                // Wait a moment for chapters to load, then set chapter
                setTimeout(() => {
                    this.chapterSelect.value = chapterName;
                    this.onChapterChange();
                }, 100);
            }

            onSeriesChange() {
                const seriesName = this.seriesSelect.value;
                this.toggleImportSection(!seriesName);

                if (!seriesName) {
                    this.chapterSelect.innerHTML = '<option value="">Select series first</option>';
                    this.chapterSelect.disabled = true;
                    return;
                }

                const series = this.seriesData.find(s => s.name === seriesName);
                if (!series) return;

                this.currentSeries = seriesName;
                this.chapterSelect.disabled = false;
                this.chapterSelect.innerHTML = '<option value="">Select a chapter...</option>';

                series.chapters.forEach(chapter => {
                    const option = document.createElement('option');
                    option.value = chapter.name;
                    const status = chapter.is_complete ? '✅' : '⚠️';
                    option.textContent = `${chapter.name} ${status} (${chapter.page_count} pages)`;
                    this.chapterSelect.appendChild(option);
                });

                this.status.textContent = `${series.chapters.length} chapters available`;
            }

            async onChapterChange() {
                const chapterName = this.chapterSelect.value;
                if (!chapterName || !this.currentSeries) return;

                this.currentChapter = chapterName;
                await this.loadChapter();
            }

            async loadChapter() {
                if (!this.currentSeries || !this.currentChapter) return;

                this.status.textContent = 'Loading infinite chapters...';
                this.comicContainer.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading infinite chapters...</p></div>';

                try {
                    // Extract chapter number from chapter name (e.g., "chapter_1" -> 1)
                    const chapterNum = parseInt(this.currentChapter.replace('chapter_', ''));
                    this.currentStartChapter = chapterNum; // Store for content polling

                    // Load infinite chapters starting from current chapter
                    const response = await fetch(`${this.apiBase}/infinite-chapters/${this.currentSeries}/${chapterNum}`);
                    const data = await response.json();

                    if (data.chapters.length === 0) {
                        this.comicContainer.innerHTML = '<div class="error">No chapters found.</div>';
                        return;
                    }

                    this.chaptersData = data.chapters;
                    this.renderInfiniteChapters(data.chapters);

                    // Show chapter indicator
                    this.chapterIndicator.classList.remove('hidden');
                    this.updateChapterIndicator();

                    // Show download status if there are background downloads
                    this.checkDownloadStatus();

                    const totalPages = data.chapters.reduce((sum, ch) => sum + ch.page_count, 0);
                    this.status.textContent = `Reading: ${this.currentSeries} - ${data.chapters.length} chapters (${totalPages} pages total)`;

                    // Save to recent chapters
                    await this.saveRecentChapter();

                } catch (error) {
                    this.comicContainer.innerHTML = '<div class="error">Error loading chapters. Please try again.</div>';
                    this.status.textContent = 'Error loading chapters';
                    console.error('Error loading chapters:', error);
                }
            }

            renderInfiniteChapters(chaptersData) {
                // Set initial setup flag to prevent intersection observer updates during DOM insertion
                this.isInitialSetup = true;
                console.log('[INIT] Starting initial setup, disabling intersection observer updates');

                this.comicContainer.innerHTML = '';
                this.chapterBoundaries = []; // Keep for backward compatibility

                chaptersData.forEach((chapter, chapterIndex) => {
                    // Add chapter divider (except for first chapter)
                    if (chapterIndex > 0) {
                        const divider = document.createElement('div');
                        divider.className = 'chapter-divider';
                        divider.innerHTML = `<div class="chapter-divider-text">Chapter ${chapter.chapter_num}</div>`;
                        this.comicContainer.appendChild(divider);
                    }

                    // Create chapter container for Intersection Observer
                    const chapterContainer = document.createElement('div');
                    chapterContainer.className = 'chapter-container';
                    chapterContainer.dataset.chapterNum = chapter.chapter_num;

                    // Add all images for this chapter
                    chapter.images.forEach((imageUrl, pageIndex) => {
                        const pageDiv = document.createElement('div');
                        pageDiv.className = 'comic-page';
                        pageDiv.dataset.chapterNum = chapter.chapter_num;
                        pageDiv.dataset.pageNum = pageIndex + 1;

                        const img = document.createElement('img');
                        img.src = imageUrl;
                        img.alt = `Chapter ${chapter.chapter_num} Page ${pageIndex + 1}`;
                        img.loading = 'lazy'; // Lazy load images

                        pageDiv.appendChild(img);
                        chapterContainer.appendChild(pageDiv);
                    });

                    this.comicContainer.appendChild(chapterContainer);

                    // Observe this chapter for scroll tracking
                    this.chapterObserver.observe(chapterContainer);
                });

                // Set initial chapter indicator
                console.log('[INIT] chaptersData:', chaptersData);
                console.log('[INIT] chaptersData.length:', chaptersData.length);
                if (chaptersData.length > 0) {
                    console.log('[INIT] First chapter data:', chaptersData[0]);
                    console.log('[INIT] Setting currentDisplayChapter to:', chaptersData[0].chapter_num);
                    this.currentDisplayChapter = chaptersData[0].chapter_num;
                    this.chapterIndicator.textContent = `Chapter ${chaptersData[0].chapter_num}`;
                    console.log('[INIT] Chapter indicator set to:', this.chapterIndicator.textContent);
                } else {
                    console.log('[INIT] No chapters data available');
                }

                // Enable intersection observer updates after DOM has settled
                setTimeout(() => {
                    this.isInitialSetup = false;
                    console.log('[INIT] Initial setup complete, enabling intersection observer updates');
                }, 500); // Wait 500ms for DOM to settle

                // Force layout calculation for accurate boundaries (keep for compatibility)
                setTimeout(() => this.updateChapterBoundaries(), 1000);
            }

            updateChapterBoundaries() {
                // Recalculate chapter boundaries based on actual rendered positions
                this.chapterBoundaries = [];
                const pages = this.comicContainer.querySelectorAll('.comic-page');
                let currentChapter = null;
                let chapterStartY = 0;

                pages.forEach((page, index) => {
                    const chapterNum = parseInt(page.dataset.chapterNum);

                    if (currentChapter !== chapterNum) {
                        // Finish previous chapter
                        if (currentChapter !== null) {
                            this.chapterBoundaries.push({
                                chapterNum: currentChapter,
                                startY: chapterStartY,
                                endY: page.offsetTop
                            });
                        }

                        // Start new chapter
                        currentChapter = chapterNum;
                        chapterStartY = page.offsetTop;
                    }
                });

                // Add the last chapter
                if (currentChapter !== null && pages.length > 0) {
                    const lastPage = pages[pages.length - 1];
                    this.chapterBoundaries.push({
                        chapterNum: currentChapter,
                        startY: chapterStartY,
                        endY: lastPage.offsetTop + lastPage.offsetHeight
                    });
                }
            }

            setupContentPolling() {
                // Poll every 3 seconds for new content when actively reading
                this.contentPollingInterval = setInterval(async () => {
                    await this.checkForNewContent();
                }, 3000);
            }

            async checkForNewContent() {
                if (!this.currentSeries || this.currentStartChapter === undefined || this.currentStartChapter === null) {
                    return;
                }

                try {
                    // Check if new chapters are available
                    const response = await fetch(`${this.apiBase}/infinite-chapters/${this.currentSeries}/${this.currentStartChapter}`);
                    if (response.ok) {
                        const newData = await response.json();

                        // Compare with current content
                        const currentChapterCount = this.comicContainer.querySelectorAll('.chapter-container').length;
                        const newChapterCount = newData.chapters.length;

                        if (newChapterCount > currentChapterCount) {
                            console.log(`🔄 Found ${newChapterCount - currentChapterCount} new chapters, injecting content...`);
                            await this.injectNewChapters(newData.chapters.slice(currentChapterCount));
                        }
                    }
                } catch (error) {
                    console.error('Error checking for new content:', error);
                }
            }

            async injectNewChapters(newChapters) {
                const currentScrollY = window.scrollY;

                newChapters.forEach((chapter, chapterIndex) => {
                    // Add chapter divider
                    const divider = document.createElement('div');
                    divider.className = 'chapter-divider';
                    divider.innerHTML = `<div class="chapter-divider-text">Chapter ${chapter.chapter_num}</div>`;
                    this.comicContainer.appendChild(divider);

                    // Create chapter container
                    const chapterContainer = document.createElement('div');
                    chapterContainer.className = 'chapter-container';
                    chapterContainer.dataset.chapterNum = chapter.chapter_num;

                    // Add all images for this chapter (matching renderInfiniteChapters structure)
                    chapter.images.forEach((imageUrl, pageIndex) => {
                        const pageDiv = document.createElement('div');
                        pageDiv.className = 'comic-page';
                        pageDiv.dataset.chapterNum = chapter.chapter_num;
                        pageDiv.dataset.pageNum = pageIndex + 1;

                        const img = document.createElement('img');
                        img.src = imageUrl;
                        img.alt = `Chapter ${chapter.chapter_num} Page ${pageIndex + 1}`;
                        img.loading = 'lazy'; // Lazy load images

                        pageDiv.appendChild(img);
                        chapterContainer.appendChild(pageDiv);
                    });

                    this.comicContainer.appendChild(chapterContainer);

                    // Observe this chapter for scroll tracking
                    this.chapterObserver.observe(chapterContainer);
                });

                // Maintain scroll position
                window.scrollTo(0, currentScrollY);

                console.log(`✅ Injected ${newChapters.length} new chapters seamlessly`);
            }

            updateChapterIndicator() {
                // This method is now handled by Intersection Observer
                // Keeping for backward compatibility if needed
            }

            async checkDownloadStatus() {
                try {
                    const response = await fetch(`${this.apiBase}/download-status/${this.currentSeries}`);
                    const data = await response.json();

                    const activeDownloads = data.statuses.filter(status =>
                        status.status === 'downloading' || status.status === 'pending'
                    );

                    if (activeDownloads.length > 0) {
                        this.showDownloadStatus(activeDownloads);
                    } else {
                        this.hideDownloadStatus();
                    }
                } catch (error) {
                    console.error('Error checking download status:', error);
                }
            }

            showDownloadStatus(downloads) {
                this.downloadText.textContent = `Downloading ${downloads.length} chapters...`;
                this.progressFill.style.width = '50%'; // Placeholder progress
                this.downloadStatus.classList.remove('hidden');

                // Hide after a few seconds
                setTimeout(() => this.hideDownloadStatus(), 5000);
            }

            hideDownloadStatus() {
                this.downloadStatus.classList.add('hidden');
            }

            renderChapter(imageUrls) {
                // Legacy method - redirect to infinite chapters
                const chapterData = [{
                    chapter_num: parseInt(this.currentChapter.replace('chapter_', '')),
                    chapter_name: this.currentChapter,
                    images: imageUrls,
                    page_count: imageUrls.length,
                    is_complete: true
                }];
                this.renderInfiniteChapters(chapterData);
            }

            async saveRecentChapter() {
                try {
                    await fetch(`${this.apiBase}/recent`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            series: this.currentSeries,
                            chapter: this.currentChapter,
                            last_read: new Date().toISOString(),
                            page_position: 0
                        })
                    });

                    // Reload recent chapters
                    await this.loadRecent();
                } catch (error) {
                    console.error('Error saving recent chapter:', error);
                }
            }

            setupKeyboardShortcuts() {
                document.addEventListener('keydown', (e) => {
                    switch(e.key) {
                        case 'ArrowUp':
                        case 'k':
                            window.scrollBy(0, -100);
                            e.preventDefault();
                            break;
                        case 'ArrowDown':
                        case 'j':
                            window.scrollBy(0, 100);
                            e.preventDefault();
                            break;
                        case ' ':
                            window.scrollBy(0, window.innerHeight * 0.8);
                            e.preventDefault();
                            break;
                        case 'Home':
                            window.scrollTo(0, 0);
                            e.preventDefault();
                            break;
                        case 'End':
                            window.scrollTo(0, document.body.scrollHeight);
                            e.preventDefault();
                            break;
                    }
                });
            }
        }

        // Import manga function
        async function importManga() {
            const urlInput = document.getElementById('mangaUrl');
            const importBtn = document.getElementById('importBtn');
            const importStatus = document.getElementById('importStatus');

            const url = urlInput.value.trim();

            if (!url) {
                importStatus.textContent = 'Please enter a RavenScans URL';
                importStatus.style.color = '#ff6b6b';
                return;
            }

            // Basic URL validation
            if (!url.includes('ravenscans.com')) {
                importStatus.textContent = 'Please enter a valid RavenScans URL';
                importStatus.style.color = '#ff6b6b';
                return;
            }

            // Disable button and show loading state
            importBtn.disabled = true;
            importBtn.textContent = 'Importing...';
            importStatus.textContent = 'Extracting manga information...';
            importStatus.style.color = '#cccccc';

            try {
                const response = await fetch(`${this.apiBase}/import-manga`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: url })
                });

                const result = await response.json();

                if (response.ok) {
                    importStatus.textContent = `✅ Successfully imported: ${result.series} - Chapter ${result.chapter}`;
                    importStatus.style.color = '#4caf50';
                    urlInput.value = '';

                    // Refresh the series list to show the new manga
                    window.location.reload();
                } else {
                    importStatus.textContent = `❌ Error: ${result.detail || 'Import failed'}`;
                    importStatus.style.color = '#ff6b6b';
                }
            } catch (error) {
                importStatus.textContent = `❌ Network error: ${error.message}`;
                importStatus.style.color = '#ff6b6b';
            } finally {
                // Re-enable button
                importBtn.disabled = false;
                importBtn.textContent = 'Import';
            }
        }

        // Start the comic reader when page loads
        document.addEventListener('DOMContentLoaded', () => {
            new ComicReader();
        });
    </script>
</body>
</html>
        """

    def run(self, auto_open: bool = True):
        """Run the web server."""
        logger.info("🔥 Starting RipRaven Web Comic Reader on http://localhost:%d", self.port)

        if auto_open:
            # Open browser after a short delay
            import threading
            def open_browser():
                import time
                time.sleep(1.5)  # Wait for server to start
                webbrowser.open(f"http://localhost:{self.port}")

            threading.Thread(target=open_browser, daemon=True).start()

        # Run the server
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )


def main():
    """Main function to start the web server."""
    import sys

    downloads_dir = "../data/ripraven/downloads"
    port = 8000

    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            logger.info("🔥 RipRaven Web Comic Reader")
            logger.info("Usage: python web_reader.py [downloads_folder] [port]")
            logger.info("Example: python web_reader.py downloads 8080")
            return

        downloads_dir = sys.argv[1]

    if len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            logger.error("❌ Invalid port number")
            return

    server = ComicWebServer(downloads_dir, port)
    server.run(auto_open=True)


if __name__ == "__main__":
    main()
