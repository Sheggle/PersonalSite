#!/usr/bin/env python3
"""
RipRaven Comic Reader - GUI app for reading downloaded comics
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from pathlib import Path
from PIL import Image, ImageTk
import glob


class ComicReader:
    def __init__(self, downloads_dir="../data/ripraven/downloads"):
        self.downloads_dir = Path(downloads_dir)
        self.current_series = None
        self.current_chapter = None
        self.current_page = 0
        self.images = []
        self.photo_cache = {}  # Cache for loaded images

        # Setup GUI
        self.root = tk.Tk()
        self.root.title("🔥 RipRaven Comic Reader")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2b2b2b')

        # Setup scrollable canvas
        self.setup_ui()
        self.setup_keybinds()

        # Load available series
        self.load_series_list()

    def setup_ui(self):
        """Setup the user interface."""
        # Top frame for controls
        control_frame = tk.Frame(self.root, bg='#2b2b2b', height=50)
        control_frame.pack(fill='x', padx=10, pady=5)
        control_frame.pack_propagate(False)

        # Series selection
        tk.Label(control_frame, text="Series:", bg='#2b2b2b', fg='white', font=('Arial', 10)).pack(side='left', padx=(0, 5))

        self.series_var = tk.StringVar()
        self.series_combo = ttk.Combobox(control_frame, textvariable=self.series_var, width=20, state='readonly')
        self.series_combo.pack(side='left', padx=(0, 10))
        self.series_combo.bind('<<ComboboxSelected>>', self.on_series_selected)

        # Chapter selection
        tk.Label(control_frame, text="Chapter:", bg='#2b2b2b', fg='white', font=('Arial', 10)).pack(side='left', padx=(0, 5))

        self.chapter_var = tk.StringVar()
        self.chapter_combo = ttk.Combobox(control_frame, textvariable=self.chapter_var, width=15, state='readonly')
        self.chapter_combo.pack(side='left', padx=(0, 10))
        self.chapter_combo.bind('<<ComboboxSelected>>', self.on_chapter_selected)

        # Page info
        self.page_info_var = tk.StringVar(value="No chapter loaded")
        page_label = tk.Label(control_frame, textvariable=self.page_info_var, bg='#2b2b2b', fg='#cccccc', font=('Arial', 10))
        page_label.pack(side='left', padx=(10, 0))

        # Browse button
        browse_btn = tk.Button(control_frame, text="📁 Browse", command=self.browse_folder,
                              bg='#404040', fg='white', font=('Arial', 9), relief='flat')
        browse_btn.pack(side='right', padx=(0, 5))

        # Help button
        help_btn = tk.Button(control_frame, text="❓ Help", command=self.show_help,
                            bg='#404040', fg='white', font=('Arial', 9), relief='flat')
        help_btn.pack(side='right', padx=(0, 5))

        # Main canvas with scrollbar
        canvas_frame = tk.Frame(self.root, bg='#2b2b2b')
        canvas_frame.pack(fill='both', expand=True, padx=10, pady=5)

        # Canvas for comic display
        self.canvas = tk.Canvas(canvas_frame, bg='#1a1a1a', highlightthickness=0)

        # Scrollbar
        scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Pack canvas and scrollbar
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Status bar
        status_frame = tk.Frame(self.root, bg='#2b2b2b', height=25)
        status_frame.pack(fill='x', padx=10, pady=(0, 5))
        status_frame.pack_propagate(False)

        self.status_var = tk.StringVar(value="📖 RipRaven Comic Reader - Select a series and chapter to begin")
        status_label = tk.Label(status_frame, textvariable=self.status_var, bg='#2b2b2b', fg='#888888',
                               font=('Arial', 9), anchor='w')
        status_label.pack(fill='x')

    def setup_keybinds(self):
        """Setup keyboard shortcuts."""
        self.root.bind('<Key>', self.on_keypress)
        self.root.focus_set()  # Make sure window can receive key events

        # Mouse wheel scrolling
        self.canvas.bind('<MouseWheel>', self.on_mousewheel)
        self.canvas.bind('<Button-4>', self.on_mousewheel)  # Linux
        self.canvas.bind('<Button-5>', self.on_mousewheel)  # Linux

    def load_series_list(self):
        """Load available series from downloads directory."""
        if not self.downloads_dir.exists():
            self.status_var.set("❌ Downloads directory not found. Please download some comics first!")
            return

        series_dirs = [d.name for d in self.downloads_dir.iterdir() if d.is_dir()]

        if not series_dirs:
            self.status_var.set("📂 No series found. Please download some comics first!")
            return

        self.series_combo['values'] = series_dirs
        self.status_var.set(f"📚 Found {len(series_dirs)} series. Select one to begin reading!")

    def on_series_selected(self, event=None):
        """Handle series selection."""
        series_name = self.series_var.get()
        if not series_name:
            return

        self.current_series = series_name
        series_path = self.downloads_dir / series_name

        # Find available chapters
        chapter_dirs = [d.name for d in series_path.iterdir() if d.is_dir()]
        chapter_dirs.sort()  # Sort chapters numerically

        if not chapter_dirs:
            messagebox.showwarning("No Chapters", f"No chapters found for {series_name}")
            return

        self.chapter_combo['values'] = chapter_dirs
        self.chapter_var.set('')  # Clear previous selection
        self.status_var.set(f"📖 {series_name} - {len(chapter_dirs)} chapters available")

    def on_chapter_selected(self, event=None):
        """Handle chapter selection."""
        if not self.current_series or not self.chapter_var.get():
            return

        self.current_chapter = self.chapter_var.get()
        self.load_chapter()

    def load_chapter(self):
        """Load images from selected chapter."""
        if not self.current_series or not self.current_chapter:
            return

        chapter_path = self.downloads_dir / self.current_series / self.current_chapter

        # Check if chapter is complete
        completion_marker = chapter_path / "completed"
        if not completion_marker.exists():
            response = messagebox.askyesno(
                "Incomplete Chapter",
                f"Chapter {self.current_chapter} appears to be incomplete (no 'completed' marker found).\n\nDo you want to read it anyway?"
            )
            if not response:
                return

        # Find all image files
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp']
        image_files = []

        for ext in image_extensions:
            image_files.extend(glob.glob(str(chapter_path / ext)))

        # Filter out the completion marker and sort
        image_files = [f for f in image_files if not f.endswith('completed')]
        image_files.sort()

        if not image_files:
            messagebox.showerror("No Images", f"No images found in {self.current_chapter}")
            return

        self.images = image_files
        self.current_page = 0
        self.photo_cache.clear()  # Clear cache for new chapter

        self.status_var.set(f"📖 Loading {self.current_series} - {self.current_chapter} ({len(self.images)} pages)")
        self.display_chapter()

    def display_chapter(self):
        """Display all pages of the current chapter in a scrollable view."""
        if not self.images:
            return

        # Clear canvas
        self.canvas.delete("all")

        # Calculate layout
        canvas_width = self.canvas.winfo_width()
        if canvas_width <= 1:  # Canvas not initialized yet
            self.root.after(100, self.display_chapter)
            return

        y_position = 20
        max_width = min(canvas_width - 40, 1000)  # Max width with padding

        for i, image_path in enumerate(self.images):
            try:
                # Load and resize image
                img = Image.open(image_path)

                # Calculate new size maintaining aspect ratio
                img_width, img_height = img.size
                if img_width > max_width:
                    ratio = max_width / img_width
                    new_width = max_width
                    new_height = int(img_height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(img)
                self.photo_cache[i] = photo  # Cache to prevent garbage collection

                # Center image horizontally
                x_position = (canvas_width - img.width) // 2

                # Add image to canvas
                self.canvas.create_image(x_position, y_position, anchor='nw', image=photo)

                # Add page number
                page_num = i + 1
                self.canvas.create_text(x_position + 10, y_position + 10,
                                      text=f"Page {page_num}",
                                      fill='white', font=('Arial', 12, 'bold'),
                                      anchor='nw')

                # Update y position for next image
                y_position += img.height + 20

            except Exception as e:
                print(f"Error loading image {image_path}: {e}")
                # Add error placeholder
                self.canvas.create_rectangle(x_position, y_position,
                                           x_position + max_width, y_position + 100,
                                           fill='#444444', outline='#666666')
                self.canvas.create_text(x_position + max_width//2, y_position + 50,
                                      text=f"Error loading page {i+1}",
                                      fill='red', font=('Arial', 12))
                y_position += 120

        # Update scroll region
        self.canvas.configure(scrollregion=(0, 0, 0, y_position))

        # Update page info
        self.page_info_var.set(f"{len(self.images)} pages")
        self.status_var.set(f"📖 {self.current_series} - {self.current_chapter} loaded successfully!")

    def on_keypress(self, event):
        """Handle keyboard shortcuts."""
        if event.keysym == 'Up' or event.keysym == 'k':
            self.scroll_up()
        elif event.keysym == 'Down' or event.keysym == 'j':
            self.scroll_down()
        elif event.keysym == 'Page_Up':
            self.scroll_page_up()
        elif event.keysym == 'Page_Down':
            self.scroll_page_down()
        elif event.keysym == 'Home':
            self.scroll_to_top()
        elif event.keysym == 'End':
            self.scroll_to_bottom()
        elif event.keysym == 'r':
            self.reload_chapter()
        elif event.keysym == 'h':
            self.show_help()

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        if event.delta:  # Windows/MacOS
            delta = -1 * (event.delta / 120)
        else:  # Linux
            delta = -1 if event.num == 4 else 1

        self.canvas.yview_scroll(int(delta * 3), "units")

    def scroll_up(self):
        """Scroll up a little."""
        self.canvas.yview_scroll(-3, "units")

    def scroll_down(self):
        """Scroll down a little."""
        self.canvas.yview_scroll(3, "units")

    def scroll_page_up(self):
        """Scroll up one page."""
        self.canvas.yview_scroll(-1, "pages")

    def scroll_page_down(self):
        """Scroll down one page."""
        self.canvas.yview_scroll(1, "pages")

    def scroll_to_top(self):
        """Scroll to top of chapter."""
        self.canvas.yview_moveto(0)

    def scroll_to_bottom(self):
        """Scroll to bottom of chapter."""
        self.canvas.yview_moveto(1)

    def reload_chapter(self):
        """Reload current chapter."""
        if self.current_series and self.current_chapter:
            self.load_chapter()

    def browse_folder(self):
        """Browse for downloads folder."""
        folder = filedialog.askdirectory(title="Select Downloads Folder")
        if folder:
            self.downloads_dir = Path(folder)
            self.load_series_list()

    def show_help(self):
        """Show help dialog."""
        help_text = """
🔥 RipRaven Comic Reader - Keyboard Shortcuts

Navigation:
• ↑ / k        - Scroll up
• ↓ / j        - Scroll down
• Page Up      - Scroll up one page
• Page Down    - Scroll down one page
• Home         - Go to top
• End          - Go to bottom

Controls:
• r            - Reload current chapter
• h            - Show this help

Mouse:
• Scroll wheel - Navigate up/down
• Select series and chapter from dropdowns

Tips:
• All downloaded comics appear in the series dropdown
• Chapters with 'completed' markers are fully downloaded
• Images are automatically resized to fit the window
        """

        messagebox.showinfo("Help - RipRaven Comic Reader", help_text)

    def run(self):
        """Start the comic reader."""
        print("🔥 Starting RipRaven Comic Reader...")
        print("📖 Use the dropdowns to select a series and chapter")
        print("⌨️  Keyboard shortcuts: ↑↓ to scroll, h for help")

        self.root.mainloop()


def main():
    """Main function to start the comic reader."""
    import sys

    downloads_dir = "../data/ripraven/downloads"
    if len(sys.argv) > 1:
        downloads_dir = sys.argv[1]

    reader = ComicReader(downloads_dir)
    reader.run()


if __name__ == "__main__":
    main()