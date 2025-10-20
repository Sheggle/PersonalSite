#!/usr/bin/env python3
"""
RipRaven Terminal Comic Reader - Terminal-based comic reader with image preview
"""

import glob
import os
import sys
from pathlib import Path

from PIL import Image

from logging_utils import get_logger

logger = get_logger(__name__)


class TerminalComicReader:
    def __init__(self, downloads_dir="../data/ripraven/downloads"):
        self.downloads_dir = Path(downloads_dir)
        self.current_series = None
        self.current_chapter = None
        self.current_page = 0
        self.images = []

    def clear_screen(self):
        """Clear terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self):
        """Print app header."""
        logger.info("🔥" * 50)
        logger.info("🔥 RipRaven Comic Reader - Terminal Edition 🔥")
        logger.info("🔥" * 50)
        logger.info("")

    def list_series(self):
        """List available series."""
        if not self.downloads_dir.exists():
            logger.error("❌ Downloads directory not found!")
            return []

        series_dirs = [d.name for d in self.downloads_dir.iterdir() if d.is_dir()]

        if not series_dirs:
            logger.info("📂 No series found. Please download some comics first!")
            return []

        logger.info("📚 Available Series:")
        for i, series in enumerate(series_dirs, 1):
            logger.info("  %2d. %s", i, series)

        return series_dirs

    def list_chapters(self, series_name):
        """List available chapters for a series."""
        series_path = self.downloads_dir / series_name

        if not series_path.exists():
            logger.error("❌ Series '%s' not found!", series_name)
            return []

        chapter_dirs = [d.name for d in series_path.iterdir() if d.is_dir()]
        chapter_dirs.sort()

        if not chapter_dirs:
            logger.info("📂 No chapters found for %s!", series_name)
            return []

        logger.info("")
        logger.info("📖 Chapters for %s:", series_name)
        for i, chapter in enumerate(chapter_dirs, 1):
            # Check if chapter is complete
            completion_marker = series_path / chapter / "completed"
            status = "✅" if completion_marker.exists() else "⚠️ "
            logger.info("  %2d. %s %s", i, chapter, status)

        return chapter_dirs

    def load_chapter_images(self, series_name, chapter_name):
        """Load images from a chapter."""
        chapter_path = self.downloads_dir / series_name / chapter_name

        if not chapter_path.exists():
            logger.error("❌ Chapter '%s' not found!", chapter_name)
            return []

        # Check completion status
        completion_marker = chapter_path / "completed"
        if not completion_marker.exists():
            logger.warning("⚠️  Warning: Chapter appears incomplete (no 'completed' marker)")

        # Find image files
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp']
        image_files = []

        for ext in image_extensions:
            image_files.extend(glob.glob(str(chapter_path / ext)))

        # Filter and sort
        image_files = [f for f in image_files if not f.endswith('completed')]
        image_files.sort()

        if not image_files:
            logger.error("❌ No images found in %s!", chapter_name)
            return []

        logger.info("")
        logger.info("📄 Loaded %d pages from %s", len(image_files), chapter_name)
        return image_files

    def show_image_info(self, image_path, page_num, total_pages):
        """Show information about the current image."""
        try:
            img = Image.open(image_path)
            width, height = img.size
            file_size = os.path.getsize(image_path) / 1024  # KB

            logger.info("📖 Page %d/%d", page_num, total_pages)
            logger.info("📏 Dimensions: %dx%d", width, height)
            logger.info("💾 Size: %.1f KB", file_size)
            logger.info("📂 File: %s", os.path.basename(image_path))

        except Exception as e:
            logger.error("❌ Error reading image: %s", e)

    def display_image_ascii(self, image_path, width=80, height=24):
        """Display a simple ASCII representation of the image."""
        try:
            img = Image.open(image_path)

            # Convert to grayscale and resize
            img = img.convert('L')
            img = img.resize((width, height), Image.Resampling.LANCZOS)

            # ASCII characters from dark to light
            ascii_chars = " .:-=+*#%@"

            logger.info("")
            logger.info("─" * width)
            for y in range(height):
                line = ""
                for x in range(width):
                    pixel = img.getpixel((x, y))
                    char_index = pixel * (len(ascii_chars) - 1) // 255
                    line += ascii_chars[char_index]
                logger.info(line)
            logger.info("─" * width)

        except Exception as e:
            logger.error("❌ Could not display image: %s", e)

    def show_navigation_help(self):
        """Show navigation commands."""
        logger.info("")
        logger.info("⌨️  Commands:")
        logger.info("  n, next     - Next page")
        logger.info("  p, prev     - Previous page")
        logger.info("  f, first    - First page")
        logger.info("  l, last     - Last page")
        logger.info("  g <num>     - Go to page number")
        logger.info("  s, series   - Change series")
        logger.info("  c, chapter  - Change chapter")
        logger.info("  i, info     - Show image info")
        logger.info("  a, ascii    - Toggle ASCII preview")
        logger.info("  h, help     - Show this help")
        logger.info("  q, quit     - Quit reader")

    def get_user_input(self, prompt="Command"):
        """Get user input with prompt."""
        try:
            return input(f"\n{prompt} > ").strip().lower()
        except KeyboardInterrupt:
            return "quit"

    def select_series(self):
        """Interactive series selection."""
        while True:
            self.clear_screen()
            self.print_header()

            series_list = self.list_series()
            if not series_list:
                input("\nPress Enter to continue...")
                return None

            choice = self.get_user_input("Select series number (or 'q' to quit)")

            if choice in ['q', 'quit']:
                return None

            try:
                series_index = int(choice) - 1
                if 0 <= series_index < len(series_list):
                    return series_list[series_index]
                else:
                    logger.error("❌ Invalid series number!")
                    input("Press Enter to continue...")
            except ValueError:
                logger.error("❌ Please enter a valid number!")
                input("Press Enter to continue...")

    def select_chapter(self, series_name):
        """Interactive chapter selection."""
        while True:
            self.clear_screen()
            self.print_header()
            logger.info("📚 Series: %s", series_name)

            chapter_list = self.list_chapters(series_name)
            if not chapter_list:
                input("\nPress Enter to continue...")
                return None

            choice = self.get_user_input("Select chapter number (or 'b' for back, 'q' to quit)")

            if choice in ['q', 'quit']:
                return None
            elif choice in ['b', 'back']:
                return 'back'

            try:
                chapter_index = int(choice) - 1
                if 0 <= chapter_index < len(chapter_list):
                    return chapter_list[chapter_index]
                else:
                    logger.error("❌ Invalid chapter number!")
                    input("Press Enter to continue...")
            except ValueError:
                logger.error("❌ Please enter a valid number!")
                input("Press Enter to continue...")

    def read_chapter(self):
        """Main chapter reading loop."""
        if not self.images:
            logger.error("❌ No images loaded!")
            return

        show_ascii = True

        while True:
            self.clear_screen()
            self.print_header()

            # Show current page info
            current_image = self.images[self.current_page]
            total_pages = len(self.images)

            logger.info("📚 %s - %s", self.current_series, self.current_chapter)
            self.show_image_info(current_image, self.current_page + 1, total_pages)

            # Show ASCII preview if enabled
            if show_ascii:
                self.display_image_ascii(current_image, width=60, height=20)

            self.show_navigation_help()

            # Get user command
            command = self.get_user_input()

            # Process commands
            if command in ['q', 'quit']:
                break
            elif command in ['n', 'next']:
                if self.current_page < len(self.images) - 1:
                    self.current_page += 1
                else:
                    logger.info("📄 Already at last page!")
                    input("Press Enter to continue...")
            elif command in ['p', 'prev']:
                if self.current_page > 0:
                    self.current_page -= 1
                else:
                    logger.info("📄 Already at first page!")
                    input("Press Enter to continue...")
            elif command in ['f', 'first']:
                self.current_page = 0
            elif command in ['l', 'last']:
                self.current_page = len(self.images) - 1
            elif command.startswith('g '):
                try:
                    page_num = int(command.split()[1]) - 1
                    if 0 <= page_num < len(self.images):
                        self.current_page = page_num
                    else:
                        logger.error("❌ Page must be between 1 and %d!", len(self.images))
                        input("Press Enter to continue...")
                except (ValueError, IndexError):
                    logger.error("❌ Invalid page number! Use: g <number>")
                    input("Press Enter to continue...")
            elif command in ['s', 'series']:
                break  # Return to series selection
            elif command in ['c', 'chapter']:
                new_chapter = self.select_chapter(self.current_series)
                if new_chapter and new_chapter != 'back':
                    self.current_chapter = new_chapter
                    self.images = self.load_chapter_images(self.current_series, self.current_chapter)
                    self.current_page = 0
                    if not self.images:
                        break
            elif command in ['i', 'info']:
                input("Press Enter to continue...")
            elif command in ['a', 'ascii']:
                show_ascii = not show_ascii
                status = "enabled" if show_ascii else "disabled"
                logger.info("📺 ASCII preview %s", status)
                input("Press Enter to continue...")
            elif command in ['h', 'help']:
                input("Press Enter to continue...")
            else:
                logger.error("❌ Unknown command! Type 'h' for help.")
                input("Press Enter to continue...")

    def run(self):
        """Main application loop."""
        logger.info("🔥 Starting RipRaven Terminal Comic Reader...")

        while True:
            # Select series
            series = self.select_series()
            if not series:
                break

            self.current_series = series

            # Select chapter
            while True:
                chapter = self.select_chapter(series)
                if not chapter:
                    break
                elif chapter == 'back':
                    break

                self.current_chapter = chapter

                # Load chapter images
                self.images = self.load_chapter_images(series, chapter)
                if not self.images:
                    input("Press Enter to continue...")
                    continue

                self.current_page = 0

                # Read chapter
                self.read_chapter()

        self.clear_screen()
        logger.info("👋 Thanks for using RipRaven Comic Reader!")


def main():
    """Main function."""
    downloads_dir = "../data/ripraven/downloads"

    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            logger.info("🔥 RipRaven Terminal Comic Reader")
            logger.info("Usage: python terminal_reader.py [downloads_folder]")
            logger.info("")
            logger.info("A terminal-based comic reader with ASCII preview")
            return

        downloads_dir = sys.argv[1]

    reader = TerminalComicReader(downloads_dir)
    reader.run()


if __name__ == "__main__":
    main()
