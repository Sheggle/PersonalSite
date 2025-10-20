#!/usr/bin/env python3
"""
RipRaven Reader Launcher - Web-based comic reader
"""

import sys
from web_reader import ComicWebServer


def main():
    """Launch the web-based comic reader."""
    downloads_dir = "../data/ripraven/downloads"
    port = 8000

    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("🔥 RipRaven Web Comic Reader")
            print("Usage: python read.py [downloads_folder] [port]")
            print()
            print("Examples:")
            print("  python read.py                    # Use ./downloads on port 8000")
            print("  python read.py my_comics          # Use ./my_comics on port 8000")
            print("  python read.py downloads 9000     # Use ./downloads on port 9000")
            print()
            print("Features:")
            print("• 🌐 Web-based interface - works on any device")
            print("• 📱 Responsive design for mobile and desktop")
            print("• 📖 Vertical scrolling for continuous reading")
            print("• 🔄 Recent chapters tracking")
            print("• ⌨️  Keyboard shortcuts (↑↓ j/k, spacebar, home/end)")
            print("• 🚀 Auto-launches browser")
            print("• ✅ Shows completion status of downloads")
            return

        downloads_dir = sys.argv[1]

    if len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            print("❌ Invalid port number. Using default port 8000.")
            port = 8000

    print("🔥 RipRaven Web Comic Reader")
    print("=" * 40)
    print()
    print(f"📁 Comics folder: {downloads_dir}")
    print(f"🌐 Server port: {port}")
    print(f"🚀 Browser will open automatically...")
    print()
    print("💡 Tip: Press Ctrl+C to stop the server")
    print()

    try:
        server = ComicWebServer(downloads_dir, port)
        server.run(auto_open=True)
    except KeyboardInterrupt:
        print("\n👋 RipRaven server stopped. Thanks for reading!")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")


if __name__ == "__main__":
    main()