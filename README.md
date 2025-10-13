# Sheggle Starter

Minimal starter for sheggle.com:
- `backend/app.py` — FastAPI with `/api/health`
- `frontend/index.html`, `frontend/styles.css` — static site hitting the backend

## Local dev
```bash
uv sync
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
python3 -m http.server 8080 -d frontend
# visit http://localhost:8080 (it will call http://localhost:8000/api/health; adjust if needed)
```

## Server layout (recommended)
Place the repo under `/srv/personalsite/`. Your existing `sheggle.service` should point
to the backend working directory and start uvicorn on 127.0.0.1:8000.

Nginx should serve `/srv/personalsite/frontend` as web root and reverse-proxy `/api` to the backend.

Example Nginx:
```nginx
server {
  listen 80;
  server_name sheggle.com www.sheggle.com;
  return 301 https://$host$request_uri;
}
server {
  listen 443 ssl http2;
  server_name sheggle.com www.sheggle.com;

  # certbot ssl_* lines here

  root /srv/personalsite/frontend;
  index index.html;

  location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```
