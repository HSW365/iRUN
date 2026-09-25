"""Instagram Reels publishing via the Instagram API with Instagram Login (graph.instagram.com)."""
import datetime as dt
import os
import time
import requests
import db

GRAPH = "https://graph.instagram.com/v23.0"


def access_token():
    stored = db.get_token("instagram") if db.enabled() else None
    tok = (stored or {}).get("value") or os.environ.get("IG_ACCESS_TOKEN")
    if not tok:
        raise RuntimeError("No Instagram token. Add IG_ACCESS_TOKEN (see SETUP.md).")
    # Long-lived tokens last 60 days; refresh on every run (allowed once the token is >24h old).
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30)
    if r.ok and "access_token" in r.json():
        tok = r.json()["access_token"]
        exp = (dt.datetime.utcnow() + dt.timedelta(seconds=r.json().get("expires_in", 0))).isoformat() + "Z"
        if db.enabled():
            db.set_token("instagram", tok, expires_at=exp)
    elif db.enabled() and not stored:
        db.set_token("instagram", tok)
    return tok


def user_id(tok):
    uid = os.environ.get("IG_USER_ID")
    if uid:
        return uid
    return requests.get(f"{GRAPH}/me", params={"fields": "user_id,username", "access_token": tok}, timeout=30).json()["user_id"]


def publish(video_url, caption):
    tok = access_token()
    uid = user_id(tok)
    c = requests.post(f"{GRAPH}/{uid}/media", timeout=60, data={
        "media_type": "REELS", "video_url": video_url, "caption": caption[:2200],
        "share_to_feed": "true", "access_token": tok}).json()
    if "id" not in c:
        raise RuntimeError(f"IG container failed: {c}")
    cid = c["id"]
    for _ in range(60):
        time.sleep(8)
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": tok}, timeout=30).json()
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"IG processing failed: {st}")
    else:
        raise RuntimeError("IG processing timed out")
    p = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60).json()
    if "id" not in p:
        raise RuntimeError(f"IG publish failed: {p}")
    return {"post_id": p["id"]}
