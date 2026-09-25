"""TikTok Content Posting API (Direct Post, FILE_UPLOAD). Refresh token is rotated and stored in Supabase."""
import os
import time
import requests
import db

API = "https://open.tiktokapis.com/v2"


def access_token():
    ck, cs = os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"]
    stored = db.get_token("tiktok") if db.enabled() else None
    refresh = (stored or {}).get("refresh_value") or os.environ.get("TIKTOK_REFRESH_TOKEN")
    if not refresh:
        raise RuntimeError("No TikTok refresh token. Run engine/tiktok_auth.py once.")
    r = requests.post(
        f"{API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_key": ck, "client_secret": cs, "grant_type": "refresh_token", "refresh_token": refresh},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    if db.enabled():
        db.set_token("tiktok", data["access_token"], data.get("refresh_token", refresh))
    return data["access_token"]


def publish(video_path, caption):
    tok = access_token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    info = requests.post(f"{API}/post/publish/creator_info/query/", headers=h, timeout=30).json()
    opts = info.get("data", {}).get("privacy_level_options", [])
    want = os.environ.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")
    privacy = want if want in opts else ("SELF_ONLY" if "SELF_ONLY" in opts else (opts[0] if opts else "SELF_ONLY"))
    if privacy != want:
        print(f"[tiktok] {want} not allowed for this app yet (options: {opts}); posting as {privacy}. "
              "Unaudited TikTok apps can only post privately until TikTok approves the app.")

    size = os.path.getsize(video_path)
    chunk = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    count = max(1, size // chunk) if size > chunk else 1
    init = requests.post(
        f"{API}/post/publish/video/init/", headers=h, timeout=30,
        json={
            "post_info": {"title": caption[:2200], "privacy_level": privacy, "disable_duet": False,
                          "disable_comment": False, "disable_stitch": False, "is_aigc": True},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                            "total_chunk_count": count},
        },
    ).json()
    if init.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init failed: {init}")
    upload_url, publish_id = init["data"]["upload_url"], init["data"]["publish_id"]

    with open(video_path, "rb") as f:
        for i in range(count):
            start = i * chunk
            length = size - start if i == count - 1 else chunk
            f.seek(start)
            body = f.read(length)
            r = requests.put(upload_url, data=body, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{start + length - 1}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok upload chunk {i} failed: {r.status_code} {r.text[:300]}")

    for _ in range(40):
        time.sleep(6)
        st = requests.post(f"{API}/post/publish/status/fetch/", headers=h, json={"publish_id": publish_id}, timeout=30).json()
        status = st.get("data", {}).get("status")
        if status == "PUBLISH_COMPLETE":
            ids = st["data"].get("publicaly_available_post_id") or st["data"].get("publicly_available_post_id") or []
            return {"publish_id": publish_id, "post_id": str(ids[0]) if ids else None, "privacy": privacy}
        if status == "FAILED":
            raise RuntimeError(f"TikTok publish failed: {st}")
    return {"publish_id": publish_id, "post_id": None, "privacy": privacy, "note": "still processing"}
