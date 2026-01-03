#!/usr/bin/env python3
"""
Pattern Finder - Extract image URL patterns from RavenScans pages
"""

import logging
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class PatternFinder:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def extract_from_ravenscans(self, url: str) -> Optional[Tuple[str, int]]:
        """
        Extract image URL pattern from RavenScans URL.
        Returns (base_pattern, start_number) or None if not found.
        """
        logger.info("🔍 Analyzing RavenScans page: %s", url)

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html_content = response.text

            # Try RavenScans CDN first (new format)
            # Pattern: https://cdnN.ravenscans.org/SERIES_NAME/chapter-N/NUMBER.jpg
            cdn_pattern = r'https://(cdn\d+)\.ravenscans\.org/([^/]+)/([^/]+)/(\d+)\.(?:jpg|png|jpeg|webp)'
            matches = re.findall(cdn_pattern, html_content)

            if matches:
                cdn_host, series_path, chapter_path, image_num = matches[0]
                base_pattern = f"https://{cdn_host}.ravenscans.org/{series_path}/{chapter_path}/"

                image_numbers = [int(match[3]) for match in matches]
                start_number = min(image_numbers)

                logger.info("✅ Found CDN pattern: %s", base_pattern)
                logger.info("📍 Starting number: %d", start_number)
                logger.info("🔢 Found %d unique image numbers", len(set(image_numbers)))

                return base_pattern, start_number

            # Fallback to manga.pics URLs (legacy format)
            # Pattern: https://manga.pics/SERIES_NAME/chapter-N/NUMBER.jpg
            manga_pics_pattern = r'https://manga\.pics/([^/]+)/([^/]+)/(\d+)\.(?:jpg|png|jpeg|webp)'
            matches = re.findall(manga_pics_pattern, html_content)

            if matches:
                series_path, chapter_path, image_num = matches[0]
                base_pattern = f"https://manga.pics/{series_path}/{chapter_path}/"

                image_numbers = [int(match[2]) for match in matches]
                start_number = min(image_numbers)

                logger.info("✅ Found manga.pics pattern: %s", base_pattern)
                logger.info("📍 Starting number: %d", start_number)
                logger.info("🔢 Found %d unique image numbers", len(set(image_numbers)))

                return base_pattern, start_number

            # If no direct matches, try alternative patterns
            logger.info("🔍 No direct image URLs found, trying alternative detection...")

            # Look for any CDN references
            alt_cdn_pattern = r'(cdn\d+)\.ravenscans\.org/([^/\s"\']+)/([^/\s"\']+)'
            alt_matches = re.findall(alt_cdn_pattern, html_content)

            if alt_matches:
                cdn_host, series_path, chapter_path = alt_matches[0]
                base_pattern = f"https://{cdn_host}.ravenscans.org/{series_path}/{chapter_path}/"

                start_number = self._detect_start_number(base_pattern)

                if start_number is not None:
                    logger.info("✅ Found alternative CDN pattern: %s", base_pattern)
                    logger.info("📍 Detected starting number: %d", start_number)
                    return base_pattern, start_number

            # Look for any manga.pics references
            alt_pattern = r'manga\.pics/([^/\s"\']+)/([^/\s"\']+)'
            alt_matches = re.findall(alt_pattern, html_content)

            if alt_matches:
                series_path, chapter_path = alt_matches[0]
                base_pattern = f"https://manga.pics/{series_path}/{chapter_path}/"

                start_number = self._detect_start_number(base_pattern)

                if start_number is not None:
                    logger.info("✅ Found alternative manga.pics pattern: %s", base_pattern)
                    logger.info("📍 Detected starting number: %d", start_number)
                    return base_pattern, start_number

            logger.warning("❌ No image pattern found in the page")
            return None

        except Exception as e:
            logger.exception("❌ Error analyzing page")
            return None

    def _detect_start_number(self, base_pattern: str) -> Optional[int]:
        """
        Auto-detect the starting image number by testing common values.
        """
        logger.info("🔍 Auto-detecting starting number...")

        # Test common starting numbers
        test_numbers = [0, 1, 2]

        for num in test_numbers:
            test_url = f"{base_pattern}{num}.jpg"
            try:
                response = self.session.head(test_url, timeout=10)
                if response.status_code == 200:
                    logger.info("✅ Found starting number: %d", num)
                    return num
            except:
                continue

        # If jpg doesn't work, try png
        for num in test_numbers:
            test_url = f"{base_pattern}{num}.png"
            try:
                response = self.session.head(test_url, timeout=10)
                if response.status_code == 200:
                    logger.info("✅ Found starting number: %d (PNG format)", num)
                    return num
            except:
                continue

        logger.warning("⚠️ Could not detect starting number, defaulting to 0")
        return 0

    def extract_chapter_info(self, url: str) -> dict:
        """Extract series and chapter info from URL for file naming."""
        # Try to parse from RavenScans URL first
        path = urlparse(url).path
        chapter_match = re.search(r'([^/]+)-chapter-(\d+)', path)

        if chapter_match:
            series_name = chapter_match.group(1).replace('-', ' ').title()
            chapter_num = chapter_match.group(2)
            return {
                'series': series_name,
                'chapter': chapter_num,
                'title': f"{series_name} - Chapter {chapter_num}"
            }

        # Fallback to manga.pics pattern if available
        manga_match = re.search(r'manga\.pics/([^/]+)/chapter-(\d+)', url)
        if manga_match:
            series_name = manga_match.group(1).replace('-', ' ').title()
            chapter_num = manga_match.group(2)
            return {
                'series': series_name,
                'chapter': chapter_num,
                'title': f"{series_name} - Chapter {chapter_num}"
            }

        return {
            'series': 'Unknown Series',
            'chapter': '1',
            'title': 'Comic Chapter'
        }

    def parse_direct_manga_pics_url(self, url: str) -> Optional[Tuple[str, int]]:
        """
        Parse a direct manga.pics URL to extract the pattern.
        Example: https://manga.pics/call-of-the-spear/chapter-1/5.jpg
        """
        pattern = r'https://manga\.pics/([^/]+)/([^/]+)/(\d+)\.(?:jpg|png|jpeg|webp)'
        match = re.match(pattern, url)

        if match:
            series_path, chapter_path, _ = match.groups()
            base_pattern = f"https://manga.pics/{series_path}/{chapter_path}/"

            # Detect starting number
            start_number = self._detect_start_number(base_pattern)

            return base_pattern, start_number

        return None

    def parse_direct_cdn_url(self, url: str) -> Optional[Tuple[str, int]]:
        """
        Parse a direct RavenScans CDN URL to extract the pattern.
        Example: https://cdn2.ravenscans.org/the-eternal-supreme/chapter-469/5.jpg
        """
        pattern = r'https://(cdn\d+)\.ravenscans\.org/([^/]+)/([^/]+)/(\d+)\.(?:jpg|png|jpeg|webp)'
        match = re.match(pattern, url)

        if match:
            cdn_host, series_path, chapter_path, _ = match.groups()
            base_pattern = f"https://{cdn_host}.ravenscans.org/{series_path}/{chapter_path}/"

            start_number = self._detect_start_number(base_pattern)

            return base_pattern, start_number

        return None

    def find_pattern(self, url: str) -> Optional[dict]:
        """
        Compatibility helper that returns a unified payload containing the base pattern,
        detected start number, and chapter metadata for a given RavenScans, CDN, or manga.pics URL.
        """
        # Check for CDN URLs first (cdn2, cdn3, etc.)
        cdn_match = re.search(r'cdn\d+\.ravenscans\.org', url)
        if cdn_match:
            result = self.parse_direct_cdn_url(url)
        elif 'ravenscans.org' in url:
            result = self.extract_from_ravenscans(url)
        elif 'manga.pics' in url:
            result = self.parse_direct_manga_pics_url(url)
        else:
            return None

        if not result:
            return None

        base_pattern, start_number = result
        chapter_info = self.extract_chapter_info(url)

        # Ensure chapter number is returned as int when possible
        chapter_raw = chapter_info.get('chapter')
        try:
            chapter_value = int(chapter_raw)
        except (TypeError, ValueError):
            chapter_value = chapter_raw

        payload = {
            'base_pattern': base_pattern,
            'start_number': start_number,
            'series': chapter_info.get('series'),
            'chapter': chapter_value,
            'title': chapter_info.get('title')
        }

        return payload


def main():
    """Test the pattern finder."""
    import sys

    if len(sys.argv) < 2:
        logger.error("Usage: python pattern_finder.py <url>")
        logger.info("Examples:")
        logger.info("  python pattern_finder.py https://ravenscans.org/the-eternal-supreme-chapter-469/")
        logger.info("  python pattern_finder.py https://cdn2.ravenscans.org/the-eternal-supreme/chapter-469/5.jpg")
        logger.info("  python pattern_finder.py https://manga.pics/call-of-the-spear/chapter-1/5.jpg")
        return

    url = sys.argv[1]
    finder = PatternFinder()

    # Check for CDN URLs first (cdn2, cdn3, etc.)
    cdn_match = re.search(r'cdn\d+\.ravenscans\.org', url)
    if cdn_match:
        result = finder.parse_direct_cdn_url(url)
    elif 'ravenscans.org' in url:
        result = finder.extract_from_ravenscans(url)
    elif 'manga.pics' in url:
        result = finder.parse_direct_manga_pics_url(url)
    else:
        logger.error("❌ Unsupported URL format")
        return

    if result:
        base_pattern, start_number = result
        chapter_info = finder.extract_chapter_info(url)

        logger.info("📋 Results:")
        logger.info("  Base Pattern: %s", base_pattern)
        logger.info("  Start Number: %d", start_number)
        logger.info("  Chapter Info: %s", chapter_info)
    else:
        logger.error("❌ Could not extract pattern from URL")


if __name__ == "__main__":
    main()
