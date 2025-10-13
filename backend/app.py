from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Sheggle Backend", version="0.1.0")

# Allow the production site and local dev to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sheggle.com", "https://www.sheggle.com", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return JSONResponse({"ok": True, "service": "sheggle-backend"})
