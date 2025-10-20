#!/usr/bin/env python3
"""
RipRaven - Comic Scraper for RavenScans
Extracts comic panels and combines them into a single scrollable image.
"""

import os
import re
import time
import requests
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class RavenScraper:
    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with appropriate options."""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def extract_chapter_info(self, url: str) -> dict:
        """Extract chapter title and other metadata from the URL."""
        # Parse URL to get chapter info
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
        else:
            return {
                'series': 'Unknown Series',
                'chapter': '1',
                'title': 'Comic Chapter'
            }

    def get_comic_images_selenium(self, url: str) -> List[str]:
        """Extract comic image URLs using Selenium to handle dynamic content and lazy loading."""
        print(f"Loading page: {url}")
        driver = self.setup_driver()

        try:
            driver.get(url)

            # Wait for initial page load
            wait = WebDriverWait(driver, 20)

            # Wait for page to load initially
            time.sleep(3)

            print("Scrolling through page to trigger lazy loading...")

            # Scroll to trigger lazy loading
            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait for new content to load
                time.sleep(2)

                # Calculate new scroll height and compare to last height
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Scroll back to top
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # Now scroll more slowly to ensure all images are loaded
            print("Performing slow scroll to ensure all images are loaded...")
            viewport_height = driver.execute_script("return window.innerHeight")
            total_height = driver.execute_script("return document.body.scrollHeight")

            for i in range(0, total_height, viewport_height // 2):
                driver.execute_script(f"window.scrollTo(0, {i});")
                time.sleep(1)  # Give time for lazy images to load

            # Final scroll to bottom and back to top
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            print("Searching for images...")

            # Look for common comic image containers with expanded selectors
            selectors = [
                'img[src*="comic"]',
                'img[src*="chapter"]',
                'img[src*="page"]',
                'img[src*="scan"]',
                'img[data-src*="comic"]',
                'img[data-src*="chapter"]',
                'img[data-src*="page"]',
                'img[data-src*="scan"]',
                '.comic-page img',
                '.chapter-content img',
                '.reading-content img',
                '.chapter-images img',
                '.manga-reader img',
                '.comic-reader img',
                '#comic-images img',
                '#chapter-images img',
                '#reader img',
                '.wp-manga-chapter-img img',
                'img[data-src]',  # All lazy loaded images
                'img[loading="lazy"]',  # Lazy loading attribute
            ]

            image_urls = []

            # Try each selector
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Selector '{selector}' found {len(elements)} elements")
                    for element in elements:
                        # Try to get the image URL from various attributes
                        img_url = (element.get_attribute('src') or
                                 element.get_attribute('data-src') or
                                 element.get_attribute('data-lazy-src') or
                                 element.get_attribute('data-original'))

                        if img_url and self._is_valid_image_url(img_url):
                            image_urls.append(img_url)
                except Exception as e:
                    continue

            # If still no images found, try to find all images and filter them
            if not image_urls:
                print("No images found with specific selectors, searching all images...")
                all_images = driver.find_elements(By.TAG_NAME, 'img')
                print(f"Found {len(all_images)} total img elements")

                for img in all_images:
                    img_url = (img.get_attribute('src') or
                             img.get_attribute('data-src') or
                             img.get_attribute('data-lazy-src') or
                             img.get_attribute('data-original'))

                    if img_url and self._is_valid_image_url(img_url):
                        # Filter for images that look like comic pages
                        url_lower = img_url.lower()
                        if (any(keyword in url_lower for keyword in ['comic', 'chapter', 'page', 'scan', 'manga']) or
                            # Also check image dimensions (comic pages are usually tall)
                            self._check_image_dimensions(img)):
                            image_urls.append(img_url)

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in image_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            print(f"Found {len(unique_urls)} comic images")

            # Print first few URLs for debugging
            if unique_urls:
                print("Sample image URLs:")
                for i, url in enumerate(unique_urls[:3]):
                    print(f"  {i+1}: {url}")

            return unique_urls

        finally:
            driver.quit()

    def _check_image_dimensions(self, img_element) -> bool:
        """Check if image dimensions suggest it's a comic page."""
        try:
            width = img_element.get_attribute('width') or img_element.get_attribute('naturalWidth')
            height = img_element.get_attribute('height') or img_element.get_attribute('naturalHeight')

            if width and height:
                w, h = int(width), int(height)
                # Comic pages are usually taller than they are wide, and reasonably large
                return h > w and h > 300 and w > 200
        except:
            pass
        return False

    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL looks like a valid image."""
        if not url or url.startswith('data:'):
            return False

        # Check for common image extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        url_lower = url.lower()

        return any(ext in url_lower for ext in image_extensions)

    def download_image(self, url: str, filename: str) -> Optional[str]:
        """Download an image from URL."""
        try:
            print(f"Downloading: {filename}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            filepath = self.output_dir / filename
            with open(filepath, 'wb') as f:
                f.write(response.content)

            return str(filepath)
        except Exception as e:
            print(f"Failed to download {url}: {e}")
            return None

    def download_all_images(self, image_urls: List[str], chapter_info: dict) -> List[str]:
        """Download all comic images."""
        downloaded_files = []

        for i, url in enumerate(image_urls, 1):
            # Create filename
            ext = '.jpg'  # Default extension
            if '.png' in url.lower():
                ext = '.png'
            elif '.webp' in url.lower():
                ext = '.webp'

            filename = f"{chapter_info['series']}_Ch{chapter_info['chapter']}_Page{i:03d}{ext}"

            filepath = self.download_image(url, filename)
            if filepath:
                downloaded_files.append(filepath)

            # Small delay to be respectful
            time.sleep(0.5)

        return downloaded_files

    def combine_images(self, image_paths: List[str], chapter_info: dict) -> str:
        """Combine downloaded images into a single scrollable image."""
        if not image_paths:
            raise ValueError("No images to combine")

        print(f"Combining {len(image_paths)} images...")

        # Load all images and calculate total dimensions
        images = []
        total_height = 0
        max_width = 0

        for path in image_paths:
            try:
                img = Image.open(path)
                images.append(img)
                total_height += img.height
                max_width = max(max_width, img.width)
            except Exception as e:
                print(f"Failed to load image {path}: {e}")
                continue

        if not images:
            raise ValueError("No valid images loaded")

        # Create combined image
        combined = Image.new('RGB', (max_width, total_height), 'white')

        # Paste images vertically
        y_offset = 0
        for img in images:
            # Center the image if it's narrower than max_width
            x_offset = (max_width - img.width) // 2
            combined.paste(img, (x_offset, y_offset))
            y_offset += img.height

        # Save combined image
        output_filename = f"{chapter_info['title'].replace(' ', '_')}_Combined.jpg"
        output_path = self.output_dir / output_filename

        # Optimize for file size while maintaining quality
        combined.save(output_path, 'JPEG', quality=85, optimize=True)

        print(f"Combined image saved: {output_path}")
        print(f"Final dimensions: {max_width}x{total_height}")

        return str(output_path)

    def scrape_chapter(self, url: str) -> str:
        """Main method to scrape a complete chapter."""
        print(f"Starting to scrape: {url}")

        # Extract chapter information
        chapter_info = self.extract_chapter_info(url)
        print(f"Chapter info: {chapter_info}")

        # Get comic image URLs
        image_urls = self.get_comic_images_selenium(url)

        if not image_urls:
            raise ValueError("No comic images found on the page")

        # Download all images
        downloaded_files = self.download_all_images(image_urls, chapter_info)

        if not downloaded_files:
            raise ValueError("Failed to download any images")

        print(f"Successfully downloaded {len(downloaded_files)} images")

        # Combine images
        combined_path = self.combine_images(downloaded_files, chapter_info)

        # Clean up individual files (optional)
        cleanup = input("Delete individual image files? (y/N): ").lower().strip()
        if cleanup == 'y':
            for filepath in downloaded_files:
                try:
                    os.remove(filepath)
                except:
                    pass
            print("Individual files cleaned up")

        return combined_path


def main():
    """Main function to run the scraper."""
    if len(os.sys.argv) < 2:
        print("Usage: python comic_scraper.py <ravenscans_url>")
        print("Example: python comic_scraper.py https://ravenscans.com/call-of-the-spear-chapter-1/")
        return

    url = os.sys.argv[1]

    try:
        scraper = RavenScraper()
        result_path = scraper.scrape_chapter(url)
        print(f"\n✅ Success! Combined comic saved to: {result_path}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())