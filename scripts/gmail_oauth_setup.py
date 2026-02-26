#!/usr/bin/env python3
"""One-time Gmail OAuth2 setup script.

Run this on the server to generate gmail_token.json:
    python3 scripts/gmail_oauth_setup.py

Prerequisites:
1. Create a GCP project and enable Gmail API
2. Create OAuth2 credentials (Desktop app type)
3. Download the client secret JSON to /srv/personalsite/credentials/gmail_client_secret.json
4. Run this script — it will open a browser for consent (or print a URL if headless)
5. The token is saved to /srv/personalsite/credentials/gmail_token.json
"""

import os
from pathlib import Path

CREDENTIALS_DIR = Path(os.environ.get("GMAIL_CREDENTIALS_DIR", "/srv/personalsite/credentials"))
TOKEN_FILE = CREDENTIALS_DIR / "gmail-token.json"
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "personal-agent.json"
SCOPES = ["https://mail.google.com/"]


def main():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    if not CLIENT_SECRET_FILE.exists():
        print(f"ERROR: Client secret not found at {CLIENT_SECRET_FILE}")
        print("Download it from GCP Console > APIs > Credentials > OAuth 2.0 Client IDs")
        return

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")
    else:
        print("Token is still valid!")

    # Quick test
    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"Authenticated as: {profile.get('emailAddress')}")


if __name__ == "__main__":
    main()
