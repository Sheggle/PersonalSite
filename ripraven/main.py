#!/usr/bin/env python3
"""
RipRaven v2.0 - Fast async comic downloader
Extracts manga.pics patterns and downloads all images concurrently.
"""

import asyncio
import sys

from pattern_finder import PatternFinder
from async_downloader import AsyncDownloader
from logging_utils import get_logger

logger = get_logger(__name__)


async def download_chapter(url: str) -> int:
    """Download a complete chapter using the new async approach."""
    logger.info("🔥 RipRaven v2.0 - Fast Comic Downloader")
    logger.info("=" * 40)

    # Initialize components
    finder = PatternFinder()
    downloader = AsyncDownloader(output_dir="../data/ripraven/downloads", max_concurrent=30)

    try:
        # Step 1: Extract pattern from URL
        logger.info("🔍 Analyzing URL: %s", url)

        if 'ravenscans.com' in url:
            result = finder.extract_from_ravenscans(url)
        elif 'manga.pics' in url:
            result = finder.parse_direct_manga_pics_url(url)
        else:
            logger.error("❌ Unsupported URL. Please use RavenScans or direct manga.pics URLs")
            return 1

        if not result:
            logger.error("❌ Could not extract manga.pics pattern from the URL")
            return 1

        base_pattern, start_number = result
        chapter_info = finder.extract_chapter_info(url)

        logger.info("📋 Chapter: %s", chapter_info['title'])
        logger.info("🎯 Pattern: %s", base_pattern)
        logger.info("🏁 Starting from: %d", start_number)

        # Step 2: Download all images
        logger.info("")
        logger.info("🚀 Starting download...")
        downloaded_files = await downloader.find_all_images(base_pattern, start_number, chapter_info)

        if not downloaded_files:
            logger.error("❌ No images were downloaded")
            return 1

        # Step 3: Show results
        logger.info("")
        logger.info("✅ Successfully downloaded %d images!", len(downloaded_files))
        logger.info("📁 Location: %s", downloader.output_dir)

        # Show first few filenames as confirmation
        logger.info("")
        logger.info("📄 Files downloaded:")
        for i, filepath in enumerate(downloaded_files[:5], 1):
            filename = filepath.split('/')[-1]
            logger.info("  %2d. %s", i, filename)

        if len(downloaded_files) > 5:
            logger.info("  ... and %d more", len(downloaded_files) - 5)

        logger.info("")
        logger.info("💡 Tip: All pages are saved as individual files for easy viewing!")

        return 0

    except KeyboardInterrupt:
        logger.warning("❌ Download interrupted by user")
        return 1
    except Exception as e:
        logger.exception("❌ Error during download")
        logger.info("")
        logger.info("🔧 Troubleshooting:")
        logger.info("1. Check the URL is correct and accessible")
        logger.info("2. Verify your internet connection")
        logger.info("3. The site might be temporarily unavailable")
        return 1


def main():
    """Main CLI interface."""
    if len(sys.argv) > 1:
        # Command line mode
        url = sys.argv[1]
    else:
        # Interactive mode
        logger.info("🔥 RipRaven v2.0 - Fast Comic Downloader")
        logger.info("=" * 40)
        logger.info("")
        logger.info("Supported URLs:")
        logger.info("• RavenScans: https://ravenscans.com/series-name-chapter-1/")
        logger.info("• Direct manga.pics: https://manga.pics/series/chapter-1/0.jpg")
        logger.info("")
        url = input("Enter URL: ").strip()

    if not url:
        logger.error("❌ No URL provided")
        return 1

    # Run the async download
    try:
        return asyncio.run(download_chapter(url))
    except KeyboardInterrupt:
        logger.warning("❌ Interrupted by user")
        return 1


if __name__ == "__main__":
    exit(main())
