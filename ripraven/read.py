#!/usr/bin/env python3
"""
RipRaven Reader Launcher - Web-based comic reader
"""

import sys

from web_reader import ComicWebServer
from logging_utils import get_logger

logger = get_logger(__name__)


def main():
    """Launch the web-based comic reader."""
    downloads_dir = "../data/ripraven/downloads"
    port = 8000

    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            logger.info("🔥 RipRaven Web Comic Reader")
            logger.info("Usage: python read.py [downloads_folder] [port]")
            logger.info("")
            logger.info("Examples:")
            logger.info("  python read.py                    # Use ./downloads on port 8000")
            logger.info("  python read.py my_comics          # Use ./my_comics on port 8000")
            logger.info("  python read.py downloads 9000     # Use ./downloads on port 9000")
            logger.info("")
            logger.info("Features:")
            logger.info("• 🌐 Web-based interface - works on any device")
            logger.info("• 📱 Responsive design for mobile and desktop")
            logger.info("• 📖 Vertical scrolling for continuous reading")
            logger.info("• 🔄 Recent chapters tracking")
            logger.info("• ⌨️  Keyboard shortcuts (↑↓ j/k, spacebar, home/end)")
            logger.info("• 🚀 Auto-launches browser")
            logger.info("• ✅ Shows completion status of downloads")
            return

        downloads_dir = sys.argv[1]

    if len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            logger.warning("❌ Invalid port number. Using default port 8000.")
            port = 8000

    logger.info("🔥 RipRaven Web Comic Reader")
    logger.info("=" * 40)
    logger.info("")
    logger.info("📁 Comics folder: %s", downloads_dir)
    logger.info("🌐 Server port: %d", port)
    logger.info("🚀 Browser will open automatically...")
    logger.info("")
    logger.info("💡 Tip: Press Ctrl+C to stop the server")
    logger.info("")

    try:
        server = ComicWebServer(downloads_dir, port)
        server.run(auto_open=True)
    except KeyboardInterrupt:
        logger.info("👋 RipRaven server stopped. Thanks for reading!")
    except Exception as e:
        logger.exception("❌ Error starting server")


if __name__ == "__main__":
    main()
