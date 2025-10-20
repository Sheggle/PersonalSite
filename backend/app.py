from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys
import os

# Add ripraven module to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ripraven'))

from web_reader import ComicWebServer

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
project_root = os.path.dirname(os.path.dirname(__file__))
ripraven_downloads_dir = os.path.join(project_root, "data", "ripraven", "downloads")
ripraven_server = ComicWebServer(downloads_dir=ripraven_downloads_dir, port=8000)

# Mount RipRaven app under /api/ripraven
app.mount("/api/ripraven", ripraven_server.app)

@app.get("/api/health")
def health():
    return JSONResponse({"ok": True, "service": "sheggle-backend"})
