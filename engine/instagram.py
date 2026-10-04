"""Instagram Reels publishing via the Instagram API with Instagram Login (graph.instagram.com)."""
import datetime as dt
import os
import time
import requests
import accounts
import db

GRAPH = "https://graph.instagram.com/v23.0"


def access_token(account=accounts.MAIN):
    name = accounts.token_name("instagram", account)
    stored = db.get_token(name) if db.enabled() else None
    tok = (stored or {}).get("value") or (os.environ.get("IG_ACCESS_TOKEN") if account == accounts.MAIN else None)
    if not tok:
        raise RuntimeError(f"No Instagram token for @{account}. See SETUP.md.")
    # Long-lived tokens last 60 days; refresh on every run (allowed once the token is >24h old).
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30)
    if r.ok and "access_token" in r.json():
        tok = r.json()["access_token"]
        exp = (dt.datetime.utcnow() + dt.timedelta(seconds=r.json().get("expires_in", 0))).isoformat() + "Z"
        if db.enabled():
            db.set_token(name, tok, expires_at=exp)
    elif db.enabled() and not stored:
        db.set_token(name, tok)
    return tok


def user_id(tok, account=accounts.MAIN):
    uid = os.environ.get("IG_USER_ID") if account == accounts.MAIN else None
    if uid:
        return uid
    return requests.get(f"{GRAPH}/me", params={"fields": "user_id,username", "access_token": tok}, timeout=30).json()["user_id"]


def publish(video_url, caption, account=accounts.MAIN):
    tok = access_token(account)
    uid = user_id(tok, account)
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


def _wait(cid, tok):
    for _ in range(60):
        time.sleep(8)
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": tok}, timeout=30).json()
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"IG processing failed: {st}")
    raise RuntimeError("IG processing timed out")


def publish_carousel(image_urls, caption, account=accounts.MAIN):
    """2-10 public JPEG URLs -> one swipeable carousel post."""
    if not 2 <= len(image_urls) <= 10:
        raise RuntimeError(f"IG carousel needs 2-10 images, got {len(image_urls)}")
    tok = access_token(account)
    uid = user_id(tok, account)
    children = []
    for u in image_urls:
        c = requests.post(f"{GRAPH}/{uid}/media", timeout=60,
                          data={"image_url": u, "is_carousel_item": "true", "access_token": tok}).json()
        if "id" not in c:
            raise RuntimeError(f"IG carousel slide failed: {c}")
        children.append(c["id"])
    parent = requests.post(f"{GRAPH}/{uid}/media", timeout=60, data={
        "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption[:2200], "access_token": tok}).json()
    if "id" not in parent:
        raise RuntimeError(f"IG carousel container failed: {parent}")
    _wait(parent["id"], tok)
    p = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": parent["id"], "access_token": tok}, timeout=60).json()
    if "id" not in p:
        raise RuntimeError(f"IG publish failed: {p}")
    return {"post_id": p["id"]}


def metrics(media_id, tok, carousel=False):
    """Views, likes, comments, shares and saves for one post. Full numbers need the
    instagram_business_manage_insights permission; without it, likes and comments still come back."""
    out = {}
    names = "reach,likes,comments,shares,saved" if carousel else "views,reach,likes,comments,shares,saved"
    r = requests.get(f"{GRAPH}/{media_id}/insights", params={"metric": names, "access_token": tok}, timeout=30)
    if r.ok:
        for m in r.json().get("data", []):
            vals = m.get("values") or [{}]
            out[m["name"]] = int(vals[0].get("value") or 0)
    if "likes" not in out:
        b = requests.get(f"{GRAPH}/{media_id}", params={"fields": "like_count,comments_count", "access_token": tok}, timeout=30)
        if not b.ok:
            raise RuntimeError(f"IG metrics failed: {r.status_code} {r.text[:200]}")
        out.update(likes=int(b.json().get("like_count") or 0), comments=int(b.json().get("comments_count") or 0), partial=True)
    out["saves"] = out.pop("saved", 0)
    if "views" not in out:
        out["views"] = out.get("reach", 0)
    return out
