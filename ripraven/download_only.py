#!/usr/bin/env python3
"""
RipRaven - Download Only Mode
Just downloads all comic images without combining them.
"""

import sys

from comic_scraper import RavenScraper
from logging_utils import get_logger

logger = get_logger(__name__)


def main():
    """Download images only, no combining."""
    if len(sys.argv) < 2:
        logger.error("Usage: python download_only.py <ravenscans_url>")
        return

    url = sys.argv[1]

    try:
        scraper = RavenScraper()

        # Extract chapter information
        chapter_info = scraper.extract_chapter_info(url)
        logger.info("Chapter info: %s", chapter_info)

        # Get comic image URLs with enhanced lazy loading handling
        image_urls = scraper.get_comic_images_selenium(url)

        if not image_urls:
            logger.warning("❌ No comic images found on the page")
            return 1

        logger.info("📥 Downloading %d images...", len(image_urls))

        # Download all images
        downloaded_files = scraper.download_all_images(image_urls, chapter_info)

        logger.info("✅ Successfully downloaded %d images!", len(downloaded_files))
        logger.info("📁 Check the 'downloads/' folder for all individual pages")

        # List downloaded files
        logger.info("Downloaded files:")
        for i, filepath in enumerate(downloaded_files, 1):
            filename = filepath.split('/')[-1]
            logger.info("%2d. %s", i, filename)

    except Exception as e:
        logger.exception("❌ Error during download")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
