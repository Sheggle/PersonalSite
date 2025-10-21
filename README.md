# Sheggle Starter

Minimal starter for sheggle.com:
- `backend/app.py` — FastAPI with `/api/health` and the `/api/ripraven` integration
- `frontend/index.html`, `frontend/styles.css` — static site hitting the backend
- `ripraven/` — packaged comic reader mounted under `/api/ripraven`

## Local dev
```bash
uv sync
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
# visit http://127.0.0.1:8000/ (serves the frontend and backend from one process)
# RipRaven library: http://127.0.0.1:8000/ripraven
# Reader deep link: http://127.0.0.1:8000/ripraven/<series>/<chapter>
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
