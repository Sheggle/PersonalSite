import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from ripraven import create_ripraven_router

app = FastAPI(title="Sheggle Backend", version="0.1.0")

# Allow the production site and local dev to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sheggle.com", "https://www.sheggle.com", "http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RipRaven comic server
# Use absolute path relative to the project root
project_root = Path(__file__).resolve().parent.parent
frontend_dir = project_root / "frontend"
ripraven_downloads_dir = project_root / "data" / "ripraven" / "downloads"
ripraven_router = create_ripraven_router(downloads_dir=ripraven_downloads_dir)
ripraven_api = getattr(ripraven_router, "ripraven_api", None)
ripraven_static_dir = project_root / "ripraven" / "static"
ripraven_page = frontend_dir / "rip_raven.html"

# Include RipRaven routes under /api/ripraven
app.include_router(ripraven_router, prefix="/api/ripraven")


def _ripraven_home_response() -> HTMLResponse:
    if ripraven_api is not None:
        return HTMLResponse(ripraven_api.get_home_html())
    if ripraven_page.exists():
        return FileResponse(ripraven_page)
    raise HTTPException(status_code=500, detail="RipRaven home template missing")


def _ripraven_reader_response() -> HTMLResponse:
    if ripraven_api is not None:
        return HTMLResponse(ripraven_api.get_reader_html())
    if ripraven_page.exists():
        return FileResponse(ripraven_page)
    raise HTTPException(status_code=500, detail="RipRaven reader template missing")


@app.get("/ripraven")
def ripraven_root():
    return _ripraven_home_response()


def _ripraven_static_response(file_path: str) -> FileResponse:
    """Serve RipRaven static assets from the package directory."""
    static_root = ripraven_static_dir.resolve()
    target = (static_root / file_path).resolve()
    try:
        target.relative_to(static_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="RipRaven asset not found")
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type or "application/octet-stream")


@app.get("/ripraven/static/{file_path:path}", include_in_schema=False)
def ripraven_static(file_path: str):
    return _ripraven_static_response(file_path)


@app.get("/ripraven/{series_name}")
def ripraven_series(series_name: str, chapter: str | None = None):
    if chapter is not None:
        return _ripraven_reader_response()
    return _ripraven_home_response()


@app.get("/ripraven/{series_name}/{chapter_num}")
def ripraven_series_chapter(series_name: str, chapter_num: str):
    encoded = quote(series_name, safe="")
    return RedirectResponse(url=f"/ripraven/{encoded}?chapter={chapter_num}", status_code=307)


@app.get("/ripraven/", include_in_schema=False)
def ripraven_root_with_slash():
    return _ripraven_home_response()


def _is_chapter_number(s: str) -> bool:
    """Check if string is a valid chapter number (int or float like 1.1)."""
    try:
        float(s)
        return True
    except ValueError:
        return False


@app.get("/ripraven/{remaining_path:path}", include_in_schema=False)
def ripraven_catch_all(remaining_path: str, request: Request, chapter: str | None = None):
    if chapter is not None:
        return _ripraven_reader_response()
    parts = [p for p in remaining_path.split("/") if p]
    if len(parts) >= 2 and _is_chapter_number(parts[-1]):
        encoded = quote(parts[-2], safe="")
        return RedirectResponse(url=f"/ripraven/{encoded}?chapter={parts[-1]}", status_code=307)
    return _ripraven_home_response()


def _frontend_file(filename: str) -> FileResponse:
    path = frontend_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    return FileResponse(path)


@app.get("/")
def frontend_index():
    return _frontend_file("index.html")


@app.get("/styles.css", include_in_schema=False)
def frontend_styles():
    return _frontend_file("styles.css")


@app.get("/rip_raven.html", include_in_schema=False)
def legacy_ripraven_page():
    return _frontend_file("rip_raven.html")


@app.get("/api/health")
def health():
    return JSONResponse({"ok": True, "service": "sheggle-backend"})
