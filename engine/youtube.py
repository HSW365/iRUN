"""YouTube Shorts upload (YouTube Data API v3, resumable upload). A vertical video under 3 minutes is a Short.

Needs a Google Cloud project with "YouTube Data API v3" enabled and an OAuth client (type: Desktop app).
One-time login per channel: python engine/youtube_auth.py --account hoodstar365
Note: until Google has audited the API project, videos uploaded through it are locked to private. Each upload
costs 1,600 of the project's 10,000 daily quota units, so about 6 uploads a day per project.
"""
import os

import requests

import accounts
import db

TOKEN_URL = "https://oauth2.googleapis.com/token"


def access_token(account=accounts.YT_MAIN):
    name = accounts.token_name("youtube", account)
    stored = db.get_token(name) if db.enabled() else None
    refresh = (stored or {}).get("refresh_value") or (
        os.environ.get("YOUTUBE_REFRESH_TOKEN") if account == accounts.YT_MAIN else None)
    if not refresh:
        raise RuntimeError(f"No YouTube login for @{account}. Run engine/youtube_auth.py --account {account} once.")
    data = requests.post(TOKEN_URL, timeout=30, data={
        "client_id": os.environ["YOUTUBE_CLIENT_ID"], "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": refresh, "grant_type": "refresh_token"}).json()
    if "access_token" not in data:
        raise RuntimeError(f"YouTube token refresh failed: {data}")
    return data["access_token"]


def publish(video_path, title, description, tags=(), account=accounts.YT_MAIN):
    tok = access_token(account)
    want = os.environ.get("YOUTUBE_PRIVACY", "public")
    title = title.strip()[:90]
    if "#shorts" not in (title + description).lower():
        description = description.rstrip() + "\n\n#Shorts"
    meta = {
        "snippet": {"title": title, "description": description[:4900], "tags": list(tags)[:15], "categoryId": "22"},
        "status": {"privacyStatus": want, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    size = os.path.getsize(video_path)
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        json=meta, timeout=60)
    if init.status_code != 200 or "Location" not in init.headers:
        raise RuntimeError(f"YouTube upload start failed: {init.status_code} {init.text[:400]}")
    with open(video_path, "rb") as f:
        up = requests.put(init.headers["Location"], data=f, timeout=900,
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
    if up.status_code not in (200, 201):
        raise RuntimeError(f"YouTube upload failed: {up.status_code} {up.text[:400]}")
    body = up.json()
    got = body.get("status", {}).get("privacyStatus")
    if got and got != want:
        print(f"[youtube] asked for {want} but YouTube set {got}. Unaudited API projects can only upload private videos.")
    return {"post_id": body["id"], "privacy": got, "url": f"https://www.youtube.com/shorts/{body['id']}"}
