#!/usr/bin/env python3
"""
RipRaven v2.0 - Fast async comic downloader
Extracts manga.pics patterns and downloads all images concurrently.
"""

import sys
import asyncio
from pattern_finder import PatternFinder
from async_downloader import AsyncDownloader


async def download_chapter(url: str) -> int:
    """Download a complete chapter using the new async approach."""
    print("🔥 RipRaven v2.0 - Fast Comic Downloader")
    print("=" * 40)

    # Initialize components
    finder = PatternFinder()
    downloader = AsyncDownloader(output_dir="../data/ripraven/downloads", max_concurrent=30)

    try:
        # Step 1: Extract pattern from URL
        print(f"🔍 Analyzing URL: {url}")

        if 'ravenscans.com' in url:
            result = finder.extract_from_ravenscans(url)
        elif 'manga.pics' in url:
            result = finder.parse_direct_manga_pics_url(url)
        else:
            print("❌ Unsupported URL. Please use RavenScans or direct manga.pics URLs")
            return 1

        if not result:
            print("❌ Could not extract manga.pics pattern from the URL")
            return 1

        base_pattern, start_number = result
        chapter_info = finder.extract_chapter_info(url)

        print(f"📋 Chapter: {chapter_info['title']}")
        print(f"🎯 Pattern: {base_pattern}")
        print(f"🏁 Starting from: {start_number}")

        # Step 2: Download all images
        print(f"\n🚀 Starting download...")
        downloaded_files = await downloader.find_all_images(base_pattern, start_number, chapter_info)

        if not downloaded_files:
            print("❌ No images were downloaded")
            return 1

        # Step 3: Show results
        print(f"\n✅ Successfully downloaded {len(downloaded_files)} images!")
        print(f"📁 Location: {downloader.output_dir}")

        # Show first few filenames as confirmation
        print(f"\n📄 Files downloaded:")
        for i, filepath in enumerate(downloaded_files[:5], 1):
            filename = filepath.split('/')[-1]
            print(f"  {i:2d}. {filename}")

        if len(downloaded_files) > 5:
            print(f"  ... and {len(downloaded_files) - 5} more")

        print(f"\n💡 Tip: All pages are saved as individual files for easy viewing!")

        return 0

    except KeyboardInterrupt:
        print("\n❌ Download interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Check the URL is correct and accessible")
        print("2. Verify your internet connection")
        print("3. The site might be temporarily unavailable")
        return 1


def main():
    """Main CLI interface."""
    if len(sys.argv) > 1:
        # Command line mode
        url = sys.argv[1]
    else:
        # Interactive mode
        print("🔥 RipRaven v2.0 - Fast Comic Downloader")
        print("=" * 40)
        print("\nSupported URLs:")
        print("• RavenScans: https://ravenscans.com/series-name-chapter-1/")
        print("• Direct manga.pics: https://manga.pics/series/chapter-1/0.jpg")
        print()
        url = input("Enter URL: ").strip()

    if not url:
        print("❌ No URL provided")
        return 1

    # Run the async download
    try:
        return asyncio.run(download_chapter(url))
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        return 1


if __name__ == "__main__":
    exit(main())
