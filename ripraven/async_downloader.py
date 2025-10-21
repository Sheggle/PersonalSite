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

        # Create completion marker file
        if downloaded_files:  # Only if we actually downloaded something
            completion_file = chapter_dir / "completed"
            try:
                completion_file.touch()
                logger.info("✅ Completion marker created: %s", completion_file)
            except Exception as e:
                logger.warning("⚠️ Could not create completion marker: %s", e)

        return downloaded_files

    async def download_specific_range(self, base_pattern: str, start: int, end: int, chapter_info: dict = None) -> List[str]:
        """
        Download a specific range of images concurrently.
        Useful when you know the exact range.
        """
        logger.info(
            "🚀 Downloading images %d-%d from: %s",
            start,
            end,
            base_pattern,
        )
        logger.info("📊 Max concurrent downloads: %d", self.max_concurrent)

        if not chapter_info:
            chapter_info = {'series': 'Unknown', 'chapter': '1'}

        # Create organized folder structure
        manga_name = chapter_info['series'].replace(' ', '_').replace('-', '_')
        chapter_folder = f"chapter_{chapter_info['chapter']}"
        chapter_dir = self.output_dir / manga_name / chapter_folder
        chapter_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        start_time = time.time()

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Create download tasks for the range
            for image_num in range(start, end + 1):
                # Try common extensions
                for ext in ['jpg', 'png', 'jpeg']:
                    url = f"{base_pattern}{image_num}.{ext}"
                    filename = f"page_{image_num:03d}.{ext}"
                    filepath = str(chapter_dir / filename)

                    task = self.download_image(session, url, filepath, image_num)
                    tasks.append((task, filepath, image_num))

            # Execute all downloads concurrently
            results = await asyncio.gather(*[task for task, _, _ in tasks], return_exceptions=True)

            # Process results
            downloaded_files = []
            successful_downloads = 0

            for i, (result, filepath, image_num) in enumerate(zip(results, [t[1] for t in tasks])):
                if isinstance(result, tuple):
                    success, _, error = result
                    if success:
                        downloaded_files.append(filepath)
                        successful_downloads += 1

        total_time = time.time() - start_time
        avg_rate = successful_downloads / total_time if total_time > 0 else 0

        logger.info("✅ Batch download complete!")
        logger.info(
            "📊 Downloaded: %d/%d images in %.1fs (%.1f img/s)",
            successful_downloads,
            end - start + 1,
            total_time,
            avg_rate,
        )

        # Create completion marker file
        if downloaded_files:  # Only if we actually downloaded something
            completion_file = chapter_dir / "completed"
            try:
                completion_file.touch()
                logger.info("✅ Completion marker created: %s", completion_file)
            except Exception as e:
                logger.warning("⚠️ Could not create completion marker: %s", e)

        return downloaded_files

    async def download_chapter_range(self, base_pattern_template: str, start_chapter: int, end_chapter: int, series_info: dict = None) -> Dict[int, List[str]]:
        """
        Download a range of chapters. Returns dict of {chapter_num: [file_paths]}.
        base_pattern_template should have {chapter} placeholder, e.g. 'https://manga.pics/series/chapter-{chapter}/'
        """
        logger.info(
            "🚀 Downloading chapters %d-%d",
            start_chapter,
            end_chapter,
        )

        if not series_info:
            series_info = {'series': 'Unknown', 'chapter': str(start_chapter)}

        results = {}

        # Download each chapter
        for chapter_num in range(start_chapter, end_chapter + 1):
            logger.info("📖 Starting Chapter %d...", chapter_num)

            # Create chapter-specific info
            chapter_info = series_info.copy()
            chapter_info['chapter'] = str(chapter_num)

            # Generate pattern for this chapter
            chapter_pattern = base_pattern_template.format(chapter=chapter_num)

            try:
                # Download this chapter
                downloaded_files = await self.find_all_images(chapter_pattern, 0, chapter_info)
                results[chapter_num] = downloaded_files

                if downloaded_files:
                    logger.info(
                        "✅ Chapter %d: %d pages downloaded",
                        chapter_num,
                        len(downloaded_files),
                    )
                else:
                    logger.warning(
                        "❌ Chapter %d: No images found",
                        chapter_num,
                    )

            except Exception as e:
                logger.error("❌ Chapter %d: Error - %s", chapter_num, e)
                results[chapter_num] = []

        return results

    async def download_chapters(self, current_series: str, chapters: list[int]) -> Dict[int, bool]:
        """
        Auto-download the next N chapters ahead of the current chapter.
        Returns dict of {chapter_num: success_status}.
        """
        logger.info(
            "🔄 Auto-downloading chapters %d",
            ', '.join(map(str, chapters)),
        )

        results = {}

        # Start downloading from the next chapter after the highest available
        for next_chapter in chapters:

            # Check if chapter already exists and is complete
            chapter_dir = self.output_dir / current_series / f"chapter_{next_chapter}"
            completion_marker = chapter_dir / "completed"

            if completion_marker.exists():
                logger.info("✅ Chapter %d already downloaded", next_chapter)
                results[next_chapter] = True
                continue

            logger.info("📥 Downloading Chapter %d...", next_chapter)

            try:
                # Try to detect the correct URL pattern for this series
                base_pattern = await self.detect_series_pattern(current_series, next_chapter)

                if not base_pattern:
                    # Fallback to standard manga.pics pattern
                    series_slug = current_series.lower().replace('_', '-').replace(' ', '-')
                    base_pattern = f"https://manga.pics/{series_slug}/chapter-{next_chapter}/"
                    logger.info("🔍 Using fallback pattern: %s", base_pattern)

                chapter_info = {
                    'series': current_series,
                    'chapter': str(next_chapter)
                }

                # Download the chapter
                downloaded_files = await self.find_all_images(base_pattern, 0, chapter_info)

                if downloaded_files:
                    logger.info(
                        "✅ Chapter %d: %d pages downloaded",
                        next_chapter,
                        len(downloaded_files),
                    )
                    results[next_chapter] = True
                else:
                    logger.warning(
                        "❌ Chapter %d: No images found (might not exist yet)",
                        next_chapter,
                    )
                    results[next_chapter] = False

            except Exception as e:
                logger.error("❌ Chapter %d: Error - %s", next_chapter, e)
                results[next_chapter] = False

        return results

    async def detect_series_pattern(self, series_name: str, chapter_num: int) -> str:
        """
        Try to detect the correct URL pattern for a series by examining existing chapters.
        Returns the base pattern URL or None if detection fails.
        """
        try:
            # Look for an existing chapter to extract the pattern
            for existing_chapter in range(1, chapter_num):
                chapter_dir = self.output_dir / series_name / f"chapter_{existing_chapter}"
                if chapter_dir.exists():
                    # Try to find pattern from existing downloads or use PatternFinder
                    from .pattern_finder import PatternFinder
                    finder = PatternFinder()

                    # Generate likely RavenScans URL for this series/chapter
                    series_slug = series_name.lower().replace('_', '-').replace(' ', '-')
                    raven_url = f"https://ravenscans.com/{series_slug}-chapter-{chapter_num}/"

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

    def get_chapter_status(self, series_name: str, chapter_num: int) -> Dict[str, any]:
        """Check if a chapter exists and is complete."""
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
