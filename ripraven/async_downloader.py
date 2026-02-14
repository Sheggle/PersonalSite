#!/usr/bin/env python3
"""
Async Downloader - Fast concurrent image downloads with progress tracking
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

import aiofiles
import aiohttp

logger = logging.getLogger(__name__)


class AsyncDownloader:
    def __init__(self, output_dir: str = "downloads", max_concurrent: int = 30):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Session configuration
        self.timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def download_image(self, session: aiohttp.ClientSession, url: str, filepath: str, image_num: int) -> Tuple[bool, int, str]:
        """
        Download a single image.
        Returns (success, image_number, error_message)
        """
        async with self.semaphore:
            try:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 404:
                        return False, image_num, "404 Not Found"
                    elif response.status != 200:
                        return False, image_num, f"HTTP {response.status}"

                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)

                    # Download and save the file
                    async with aiofiles.open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)

                    return True, image_num, ""

            except asyncio.TimeoutError:
                return False, image_num, "Timeout"
            except Exception as e:
                return False, image_num, str(e)

    async def find_all_images(self, base_pattern: str, start_number: int = 0, chapter_info: dict = None) -> List[str]:
        """
        Find all available images by testing URLs until 404.
        Returns list of downloaded file paths.
        """
        logger.info("🚀 Starting concurrent download from: %s", base_pattern)
        logger.info("📊 Max concurrent downloads: %d", self.max_concurrent)

        if not chapter_info:
            chapter_info = {'series': 'Unknown', 'chapter': '1'}

        # Create organized folder structure: downloads/<manga>/chapter_<num>/
        manga_name = chapter_info['series'].replace(' ', '_').replace('-', '_')
        chapter_folder = f"chapter_{chapter_info['chapter']}"
        chapter_dir = self.output_dir / manga_name / chapter_folder
        chapter_dir.mkdir(parents=True, exist_ok=True)

        logger.info("📁 Saving to: %s", chapter_dir)

        downloaded_files = []
        image_num = start_number
        consecutive_404s = 0
        max_consecutive_404s = 5  # Stop after 5 consecutive 404s

        # Track progress
        start_time = time.time()
        last_progress_time = start_time

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Start with a small batch to find the range
            logger.info("🔍 Detecting image range starting from %d...", start_number)

            while consecutive_404s < max_consecutive_404s:
                # Try both jpg and png extensions
                extensions = ['jpg', 'png', 'jpeg', 'webp']
                found_image = False

                for ext in extensions:
                    url = f"{base_pattern}{image_num}.{ext}"

                    # Generate clean filename: page_000.jpg, page_001.jpg, etc.
                    filename = f"page_{image_num:03d}.{ext}"
                    filepath = str(chapter_dir / filename)

                    success, _, error = await self.download_image(session, url, filepath, image_num)

                    if success:
                        downloaded_files.append(filepath)
                        consecutive_404s = 0  # Reset counter
                        found_image = True

                        # Progress update
                        current_time = time.time()
                        if current_time - last_progress_time >= 1.0:  # Update every second
                            elapsed = current_time - start_time
                            rate = len(downloaded_files) / elapsed if elapsed > 0 else 0
                            logger.info(
                                "📥 Downloaded %d images | Page %d | %.1f img/s",
                                len(downloaded_files),
                                image_num,
                                rate,
                            )
                            last_progress_time = current_time

                        break  # Found the image with this extension, move to next number

                if not found_image:
                    consecutive_404s += 1

                image_num += 1

                # Safety limit to prevent infinite loops
                if image_num > start_number + 1000:
                    logger.warning("⚠️ Reached safety limit of 1000 images, stopping")
                    break

        total_time = time.time() - start_time
        avg_rate = len(downloaded_files) / total_time if total_time > 0 else 0

        logger.info("✅ Download complete!")
        logger.info(
            "📊 Total: %d images in %.1fs (%.1f img/s)",
            len(downloaded_files),
            total_time,
            avg_rate,
        )
        logger.info("📁 Saved to: %s", chapter_dir)

        if downloaded_files:
            # Create completion marker file
            completion_file = chapter_dir / "completed"
            try:
                completion_file.touch()
                logger.info("✅ Completion marker created: %s", completion_file)
            except Exception as e:
                logger.warning("⚠️ Could not create completion marker: %s", e)
        else:
            # Clean up empty chapter directory from failed download
            try:
                if chapter_dir.exists() and not any(
                    f for f in chapter_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
                ):
                    import shutil
                    shutil.rmtree(chapter_dir)
                    logger.info("🧹 Cleaned up empty chapter directory: %s", chapter_dir)
            except Exception as e:
                logger.warning("⚠️ Could not clean up empty directory: %s", e)

        return downloaded_files

    async def download_chapters(
        self,
        series_name: str,
        chapters: List[str],
        *,
        base_pattern_template: str | None = None,
        series_info: dict | None = None,
        start_number: int = 0,
    ) -> Dict[str, List[str]]:
        """
        Download one or more chapters and return downloaded file paths per chapter.

        When ``base_pattern_template`` is provided it must contain a ``{chapter}``
        placeholder that will be formatted with the chapter number to produce the
        download URL prefix. If it is omitted the downloader will attempt to detect
        a suitable pattern via ``detect_series_pattern`` and fall back to the
        standard manga.pics URL style.
        """
        if not chapters:
            return {}

        logger.info("🔄 Downloading chapters: %s", ", ".join(chapters))

        # Ensure series info always has a sensible default
        base_series_info = (series_info or {}).copy()
        if "series" not in base_series_info:
            base_series_info["series"] = series_name or "Unknown"

        results: Dict[str, List[str]] = {}

        for chapter_num in chapters:
            logger.info("📥 Downloading Chapter %s...", chapter_num)

            chapter_info = base_series_info.copy()
            chapter_info["chapter"] = chapter_num

            chapter_dir = self.output_dir / chapter_info["series"] / f"chapter_{chapter_num}"
            completion_marker = chapter_dir / "completed"

            if completion_marker.exists():
                logger.info("✅ Chapter %s already downloaded", chapter_num)
                # Collect existing files to surface consistent return data
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
                existing_files = [
                    str(path)
                    for path in sorted(chapter_dir.iterdir())
                    if path.is_file() and path.suffix.lower() in image_extensions
                ]
                results[chapter_num] = existing_files
                continue

            # Resolve the base pattern for this chapter
            # For fractional chapters (1.1), convert to URL format (1-1)
            chapter_url_format = chapter_num.replace('.', '-') if '.' in chapter_num else chapter_num
            if base_pattern_template:
                base_pattern = base_pattern_template.format(chapter=chapter_url_format)
            else:
                base_pattern = await self.detect_series_pattern(series_name, chapter_num)
                if not base_pattern:
                    series_slug = (series_name or "").lower().replace("_", "-").replace(" ", "-")
                    base_pattern = f"https://manga.pics/{series_slug}/chapter-{chapter_url_format}/"
                    logger.info("🔍 Using fallback pattern: %s", base_pattern)

            try:
                downloaded_files = await self.find_all_images(base_pattern, start_number, chapter_info)
                if downloaded_files:
                    logger.info(
                        "✅ Chapter %s: %d pages downloaded",
                        chapter_num,
                        len(downloaded_files),
                    )
                else:
                    logger.warning("❌ Chapter %s: No images found", chapter_num)
                results[chapter_num] = downloaded_files
            except Exception as e:
                logger.error("❌ Chapter %s: Error - %s", chapter_num, e)
                results[chapter_num] = []

        return results

    async def detect_series_pattern(self, series_name: str, chapter_num: str) -> str:
        """
        Try to detect the correct URL pattern for a series by examining existing chapters.
        Returns the base pattern URL or None if detection fails.
        """
        try:
            # Convert to int for iteration if possible, otherwise just check chapter 1
            try:
                max_chapter = int(float(chapter_num))
            except ValueError:
                max_chapter = 2

            # Look for an existing chapter to extract the pattern
            for existing_chapter in range(1, max_chapter):
                chapter_dir = self.output_dir / series_name / f"chapter_{existing_chapter}"
                if chapter_dir.exists():
                    # Try to find pattern from existing downloads or use PatternFinder
                    from .pattern_finder import PatternFinder
                    finder = PatternFinder()

                    # Generate likely RavenScans URL for this series/chapter
                    # Convert fractional chapters to URL format (1.1 -> 1-1)
                    series_slug = series_name.lower().replace('_', '-').replace(' ', '-')
                    chapter_url_format = chapter_num.replace('.', '-') if '.' in chapter_num else chapter_num
                    raven_url = f"https://cdn2.ravenscans.org/{series_slug}/chapter-{chapter_url_format}/"

                    try:
                        # Try to extract pattern
                        result = finder.find_pattern(raven_url)
                        if result and result.get('base_pattern'):
                            pattern = result['base_pattern']
                            logger.info("🔍 Detected pattern from RavenScans: %s", pattern)
                            return pattern
                    except Exception as e:
                        logger.warning("⚠️ Pattern detection failed: %s", e)

                    break

        except Exception as e:
            logger.warning("⚠️ Error in pattern detection: %s", e)

        return None

    def get_chapter_status(self, series_name: str, chapter_num: str) -> Dict[str, any]:
        """Check if a chapter exists and is complete.

        Args:
            series_name: The series name
            chapter_num: Chapter number as string (e.g., '1', '1.1', '10')
        """
        chapter_dir = self.output_dir / series_name / f"chapter_{chapter_num}"
        completion_marker = chapter_dir / "completed"

        if not chapter_dir.exists():
            return {"exists": False, "complete": False, "page_count": 0}

        # Count pages
        image_files = []
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

        for file_path in chapter_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                image_files.append(file_path.name)

        return {
            "exists": True,
            "complete": completion_marker.exists(),
            "page_count": len(image_files)
        }
