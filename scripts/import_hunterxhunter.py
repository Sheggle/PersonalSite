"""Import Hunter x Hunter chapters from hunterxhunter.com.lv into the ripraven tree.

The main ripraven scraper (`ripraven/scraper.py`) is ravenscans-specific: it drives
a real Chrome under xvfb purely to clear Cloudflare. This source has no challenge at
all, so a plain stdlib HTTP client is enough and ~20x faster.

Two image layouts exist on this site and both are handled:
    .../uploads/manga/chapter-330/01-hunter-x-hunter-chapter-330.webp   (most chapters)
    .../uploads/01-hunter-x-hunter-chapter-416-early.webp               (flat, suffixed)

Resumable: a chapter directory holding a `completed` marker is skipped, so re-running
after an interruption only fetches what is missing.

Usage:  python3 scripts/import_hunterxhunter.py [first_chapter] [last_chapter]
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from random import uniform

SERIES = "Hunter_X_Hunter"
BASE = "https://hunterxhunter.com.lv/manga/hunter-x-hunter-chapter-%s/"
ROOT = Path("/srv/personalsite/data/ripraven")
DOWNLOADS = ROOT / "downloads" / SERIES
INDEX = ROOT / "series_index.json"
LOG = Path("/tmp/hxh_import.log")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Page images are named "<pagenum>-hunter-x-hunter-chapter-<N>[-suffix].<ext>".
# Anchoring on the chapter number keeps out next-chapter thumbnails and site
# chrome (favicons are "cropped-hunter-x-hunter-32x32.webp" — no numeric prefix).
PAGE_URL_TMPL = (r"https://img\.hunterxhunter\.com\.lv/uploads/[^\"'\s>)]*?"
                 r"(\d+)-hunter-x-hunter-chapter-%s(?:-[a-z0-9]+)*"
                 r"\.(?:webp|jpe?g|png)")
# Chapters 411-414 were uploaded under raw camera filenames ("IMG_4233.jpeg")
# that carry no chapter token, so the pattern above cannot see them. For those,
# fall back to every <img src> under /uploads/ in document order, minus the
# site chrome (favicons, cover) which is the only other thing served from there.
FALLBACK_SRC_RE = re.compile(
    r"src=\"(https://img\.hunterxhunter\.com\.lv/uploads/[^\"]+"
    r"\.(?:webp|jpe?g|png))\"", re.IGNORECASE)
CHROME_MARKERS = ("cropped-", "cover", "logo", "icon")
# Stop probing once this many consecutive chapter URLs 404.
MISS_STREAK_LIMIT = 5
WORKERS = 10
ATTEMPTS = 3


def log(msg):
    line = "%s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def fetch(url, referer=None, timeout=60):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout).read()


def fetch_retrying(url, referer=None):
    for attempt in range(ATTEMPTS):
        try:
            return fetch(url, referer)
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 404:
                raise
            if attempt == ATTEMPTS - 1:
                raise
            # Back off harder when the site is rate-limiting us.
            delay = (4.0 if code in (403, 429) else 1.5) * (attempt + 1)
            log("    retry %d/%d after %s (%s)" % (attempt + 1, ATTEMPTS, e, url))
            time.sleep(delay)


def chapter_pages(chapter, html):
    """Page image URLs for `chapter`, ordered by the page number in the filename."""
    matches = list(re.finditer(PAGE_URL_TMPL % re.escape(str(chapter)), html,
                               re.IGNORECASE))
    seen, ordered = set(), []
    for m in matches:
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            ordered.append((int(m.group(1)), url))
    if ordered:
        by_page = sorted(ordered, key=lambda t: t[0])
        if [u for _, u in by_page] != [u for _, u in ordered]:
            log("    note: document order != page-number order, using page numbers")
        return [u for _, u in by_page]

    seen, fallback = set(), []
    for url in FALLBACK_SRC_RE.findall(html):
        name = url.rsplit("/", 1)[1].lower()
        if any(marker in name for marker in CHROME_MARKERS) or url in seen:
            continue
        seen.add(url)
        fallback.append(url)
    if fallback:
        log("    ch %s: untagged filenames, using document order (%d pages)"
            % (chapter, len(fallback)))
    return fallback


def import_chapter(chapter):
    dest = DOWNLOADS / ("chapter_%s" % chapter)
    if (dest / "completed").exists():
        return "skip"

    page_url = BASE % chapter
    try:
        html = fetch_retrying(page_url).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "404"
        raise

    urls = chapter_pages(chapter, html)
    if not urls:
        log("  ch %s: page exists but no images matched" % chapter)
        return "empty"

    dest.mkdir(parents=True, exist_ok=True)
    results = [None] * len(urls)

    def grab(i_url):
        i, url = i_url
        ext = "." + url.rsplit(".", 1)[1].lower()
        out = dest / ("page_%03d%s" % (i, ext))
        data = fetch_retrying(url, referer=page_url)
        out.write_bytes(data)
        results[i] = len(data)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(grab, enumerate(urls)))

    if any(r is None for r in results):
        log("  ch %s: INCOMPLETE, not marking done" % chapter)
        return "partial"

    (dest / "completed").write_text("")
    log("  ch %s: %d pages, %.1f MB" % (chapter, len(urls), sum(results) / 1e6))
    return "ok"


def update_index():
    """Patch series_index.json from disk — it does not notice manual edits itself."""
    state = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    chapters = {}
    for d in DOWNLOADS.iterdir():
        if not d.is_dir():
            continue
        pages = [p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
        chapters[d.name] = {
            "is_complete": (d / "completed").exists(),
            "page_count": len(pages),
            "last_modified": datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
        }
    state[SERIES] = chapters
    tmp = INDEX.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(INDEX)
    return chapters


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000
    DOWNLOADS.mkdir(parents=True, exist_ok=True)

    tally = {"ok": 0, "skip": 0, "404": 0, "empty": 0, "partial": 0}
    misses, chapter = 0, first
    started = time.time()

    while chapter <= last and misses < MISS_STREAK_LIMIT:
        try:
            outcome = import_chapter(chapter)
        except Exception as e:
            log("  ch %s: FAILED %s" % (chapter, e))
            outcome = "partial"
        tally[outcome] += 1
        misses = misses + 1 if outcome == "404" else 0
        if outcome == "ok":
            update_index()
            time.sleep(uniform(0.1, 0.3))
        chapter += 1

    chapters = update_index()
    complete = sum(1 for c in chapters.values() if c["is_complete"])
    log("done in %.1f min | %s | on disk: %d chapters (%d complete), %d pages"
        % ((time.time() - started) / 60, tally, len(chapters), complete,
           sum(c["page_count"] for c in chapters.values())))


if __name__ == "__main__":
    main()
