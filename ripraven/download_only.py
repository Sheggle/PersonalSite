#!/usr/bin/env python3
"""
RipRaven - Download Only Mode
Just downloads all comic images without combining them.
"""

import sys
from comic_scraper import RavenScraper


def main():
    """Download images only, no combining."""
    if len(sys.argv) < 2:
        print("Usage: python download_only.py <ravenscans_url>")
        return

    url = sys.argv[1]

    try:
        scraper = RavenScraper()

        # Extract chapter information
        chapter_info = scraper.extract_chapter_info(url)
        print(f"Chapter info: {chapter_info}")

        # Get comic image URLs with enhanced lazy loading handling
        image_urls = scraper.get_comic_images_selenium(url)

        if not image_urls:
            print("❌ No comic images found on the page")
            return 1

        print(f"\n📥 Downloading {len(image_urls)} images...")

        # Download all images
        downloaded_files = scraper.download_all_images(image_urls, chapter_info)

        print(f"\n✅ Successfully downloaded {len(downloaded_files)} images!")
        print(f"📁 Check the 'downloads/' folder for all individual pages")

        # List downloaded files
        print("\nDownloaded files:")
        for i, filepath in enumerate(downloaded_files, 1):
            filename = filepath.split('/')[-1]
            print(f"  {i:2d}. {filename}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())