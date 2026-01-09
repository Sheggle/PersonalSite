#!/usr/bin/env python3
"""
Pattern Finder - Extract image URL patterns from RavenScans pages
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
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
        """Extract series and chapter info from URL for file naming.

        Handles fractional chapters like chapter-1-1 (1.1), chapter-9-5 (9.5).
        """
        # Try to parse from RavenScans URL first
        path = urlparse(url).path
        # Match chapter numbers including fractional: chapter-1, chapter-1-1, chapter-10-5
        chapter_match = re.search(r'([^/]+)-chapter-(\d+(?:-\d+)?)', path)

        if chapter_match:
            series_name = chapter_match.group(1).replace('-', ' ').title()
            chapter_raw = chapter_match.group(2)
            # Convert 1-1 to 1.1, 9-5 to 9.5, keep 10 as 10
            chapter_num = chapter_raw.replace('-', '.')
            return {
                'series': series_name,
                'chapter': chapter_num,
                'title': f"{series_name} - Chapter {chapter_num}"
            }

        # Fallback to manga.pics pattern if available
        manga_match = re.search(r'manga\.pics/([^/]+)/chapter-(\d+(?:-\d+)?)', url)
        if manga_match:
            series_name = manga_match.group(1).replace('-', ' ').title()
            chapter_raw = manga_match.group(2)
            chapter_num = chapter_raw.replace('-', '.')
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

        # Keep chapter as string to support fractional chapters (1.1, 1.2, etc.)
        chapter_value = chapter_info.get('chapter', '1')

        payload = {
            'base_pattern': base_pattern,
            'start_number': start_number,
            'series': chapter_info.get('series'),
            'chapter': chapter_value,
            'title': chapter_info.get('title')
        }

        return payload

    def get_series_url_from_chapter_url(self, chapter_url: str) -> Optional[str]:
        """
        Derive the series landing page URL from a chapter URL.
        E.g., https://ravenscans.org/series-name-chapter-1-1/ -> https://ravenscans.org/manga/series-name/
        """
        path = urlparse(chapter_url).path
        # Match series-name-chapter-X pattern
        match = re.search(r'/([^/]+)-chapter-\d+(?:-\d+)?/?$', path)
        if match:
            series_slug = match.group(1)
            return f"https://ravenscans.org/manga/{series_slug}/"
        return None

    def scrape_chapter_list(self, series_url: str) -> List[dict]:
        """
        Scrape the list of chapters from a Ravenscans series page.
        Returns list of dicts with 'number' (str) and 'url' keys, sorted by chapter.
        """
        logger.info("🔍 Scraping chapter list from: %s", series_url)

        try:
            response = self.session.get(series_url, timeout=30)
            response.raise_for_status()
            html_content = response.text

            # Find all chapter links - pattern: href="...chapter-X..." or href="...chapter-X-Y..."
            # Ravenscans uses links like: /series-name-chapter-10/ or /series-name-chapter-1-1/
            chapter_pattern = r'href="(https?://[^"]*-chapter-(\d+(?:-\d+)?)[^"]*)"'
            matches = re.findall(chapter_pattern, html_content)

            if not matches:
                logger.warning("❌ No chapter links found on page")
                return []

            # Deduplicate and extract chapter info
            seen = set()
            chapters = []
            for url, chapter_raw in matches:
                chapter_num = chapter_raw.replace('-', '.')
                if chapter_num not in seen:
                    seen.add(chapter_num)
                    chapters.append({
                        'number': chapter_num,
                        'url': url
                    })

            # Sort chapters by numeric value (handles 1, 1.1, 1.2, 2, 10, etc.)
            def chapter_sort_key(ch):
                parts = ch['number'].split('.')
                try:
                    if len(parts) == 1:
                        return (float(parts[0]), 0)
                    else:
                        return (float(parts[0]), float(parts[1]))
                except ValueError:
                    return (0, 0)

            chapters.sort(key=chapter_sort_key)

            logger.info("✅ Found %d chapters", len(chapters))
            return chapters

        except Exception as e:
            logger.exception("❌ Error scraping chapter list")
            return []


class ChapterListCache:
    """Cache for chapter lists scraped from Ravenscans."""

    def __init__(self, cache_dir: str | Path = "../data/ripraven"):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "chapter_cache.json"
        self._cache = self._load_cache()
        self._finder = PatternFinder()

    def _load_cache(self) -> dict:
        """Load cache from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("⚠️ Could not load chapter cache: %s", e)
        return {}

    def _save_cache(self):
        """Save cache to file."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning("⚠️ Could not save chapter cache: %s", e)

    def _normalize_series_key(self, series_name: str) -> str:
        """Normalize series name for cache key."""
        return series_name.lower().replace(' ', '_').replace('-', '_')

    def get_chapters(self, series_name: str) -> Optional[List[dict]]:
        """Get cached chapter list for a series."""
        key = self._normalize_series_key(series_name)
        entry = self._cache.get(key)
        if entry:
            return entry.get('chapters', [])
        return None

    def set_chapters(self, series_name: str, chapters: List[dict], series_url: str = None):
        """Cache chapter list for a series."""
        key = self._normalize_series_key(series_name)
        self._cache[key] = {
            'chapters': chapters,
            'series_url': series_url,
            'last_updated': datetime.now().isoformat()
        }
        self._save_cache()

    def get_series_url(self, series_name: str) -> Optional[str]:
        """Get cached series URL."""
        key = self._normalize_series_key(series_name)
        entry = self._cache.get(key)
        if entry:
            return entry.get('series_url')
        return None

    def refresh_chapters(self, series_name: str, series_url: str = None) -> List[dict]:
        """Refresh chapter list from Ravenscans."""
        url = series_url or self.get_series_url(series_name)
        if not url:
            logger.warning("⚠️ No series URL available for %s", series_name)
            return []

        chapters = self._finder.scrape_chapter_list(url)
        if chapters:
            self.set_chapters(series_name, chapters, url)
        return chapters

    def get_next_chapters(self, series_name: str, current_chapter: str, count: int = 3) -> List[str]:
        """
        Get the next N chapter numbers after current_chapter.
        Returns list of chapter number strings.
        """
        chapters = self.get_chapters(series_name)
        if not chapters:
            return []

        # Find current chapter index
        chapter_numbers = [ch['number'] for ch in chapters]
        try:
            current_idx = chapter_numbers.index(current_chapter)
        except ValueError:
            # Current chapter not in list, try to find closest
            logger.warning("⚠️ Chapter %s not found in cached list", current_chapter)
            return []

        # Return next N chapters
        next_chapters = chapter_numbers[current_idx + 1:current_idx + 1 + count]
        return next_chapters

    def get_chapter_url(self, series_name: str, chapter_num: str) -> Optional[str]:
        """Get the URL for a specific chapter."""
        chapters = self.get_chapters(series_name)
        if not chapters:
            return None

        for ch in chapters:
            if ch['number'] == chapter_num:
                return ch.get('url')
        return None

    def needs_refresh(self, series_name: str, current_chapter: str, lookahead: int = 3) -> bool:
        """
        Check if we need to refresh the chapter list.
        Returns True if current chapter is near the end of cached list.
        """
        chapters = self.get_chapters(series_name)
        if not chapters:
            return True

        chapter_numbers = [ch['number'] for ch in chapters]
        try:
            current_idx = chapter_numbers.index(current_chapter)
            remaining = len(chapter_numbers) - current_idx - 1
            return remaining < lookahead
        except ValueError:
            return True


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
