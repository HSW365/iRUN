"""iRun engine: pick product -> write -> voice -> render -> upload -> publish (live mode) -> log.

Usage:
  python engine/run.py                      # uses the schedule slot for the current UTC hour
  python engine/run.py --platform tiktok --product klipit --mode draft
Env IRUN_MODE=draft|live (default draft: renders + stores, never posts).
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import db  # noqa: E402
import render  # noqa: E402
import voice  # noqa: E402
import writer  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
HANDLE = os.environ.get("IRUN_HANDLE", "hsw365media")
# UTC hour -> platforms. 4 TikTok + 2 Instagram per day (8am, 11am, 2pm, 6pm ET during EDT).
SCHEDULE = {12: ["tiktok"], 15: ["tiktok", "instagram"], 18: ["tiktok"], 22: ["tiktok", "instagram"]}


def load_products():
    with open(os.path.join(ROOT, "config", "products.json")) as f:
        return json.load(f)["products"]


def sync_products(products):
    if not db.enabled():
        return
    for p in products:
        db.insert("irun_products", {"id": p["id"], "name": p["name"], "keyword": p["keyword"].upper(),
                                    "link": p["link"], "pitch": p["pitch"], "active": True}, upsert_on="id")


def pick_product(products, platform, forced=None):
    if forced:
        return next(p for p in products if p["id"] == forced)
    if db.enabled():
        rows = db.select("irun_posts", f"platform=eq.{platform}&select=product_id,created_at&order=created_at.desc&limit=50")
        recent = [r["product_id"] for r in rows]
        never = [p for p in products if p["id"] not in recent]
        if never:
            return random.choice(never)
        return max(products, key=lambda p: recent.index(p["id"]))  # least recently used
    return products[(dt.datetime.utcnow().timetuple().tm_yday * 7 + dt.datetime.utcnow().hour) % len(products)]


def recent_hooks(product_id):
    if not db.enabled():
        return []
    rows = db.select("irun_posts", f"product_id=eq.{product_id}&select=hook&order=created_at.desc&limit=8")
    return [r["hook"] for r in rows if r.get("hook")]


def cta_for(platform, kw):
    if platform == "instagram":
        return (f"Comment {kw} and I'll DM you the link",
                (f"COMMENT \"{kw}\"", f"OR DM \"{kw}\" TO @{HANDLE.upper()}"),
                f"Comment {kw} and the link lands in your DMs.")
    return (f"DM {kw} to @{HANDLE} on Instagram for the link",
            (f"DM \"{kw}\"", f"TO @{HANDLE.upper()} ON INSTAGRAM"),
            f"DM {kw} to @{HANDLE} on Instagram and the link comes straight to you. Link in bio too.")


def make_one(product, platform, mode, outdir):
    kw = product["keyword"].upper()
    spoken_cta, screen_cta, caption_cta = cta_for(platform, kw)
    angle = random.choice(product.get("angles") or [product["pitch"]])
    script = writer.write_script(product, angle, platform, spoken_cta, recent_hooks(product["id"]))
    caption = script["caption"]
    if caption_cta.lower()[:20] not in caption.lower():
        caption = f"{caption}\n\n{caption_cta}"
    caption += "\n\n" + " ".join("#" + t for t in script["hashtags"])

    os.makedirs(outdir, exist_ok=True)
    stamp = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    slug = f"{stamp}-{platform}-{product['id']}"
    work = tempfile.mkdtemp(prefix="irun-")
    audio, alen, vsrc = voice.speak(" ".join(script["beats"]), os.path.join(work, "vo.mp3"))
    video = os.path.join(outdir, f"{slug}.mp4")
    render.render(script["beats"], script["emphasis"], audio, alen, product, work, video, cta=screen_cta)
    with open(os.path.join(outdir, f"{slug}.txt"), "w") as f:
        f.write(caption + "\n\n---\n" + "\n".join(script["beats"]))

    row = {"platform": platform, "product_id": product["id"], "hook": script["beats"][0], "caption": caption,
           "script": script["beats"], "voice": vsrc, "status": "draft", "mode": mode}
    video_url = None
    if db.enabled():
        video_url = db.upload_public(video, f"{slug}.mp4")
        row["video_url"] = video_url

    if mode == "live":
        try:
            if platform == "tiktok":
                import tiktok
                res = tiktok.publish(video, caption)
            else:
                import instagram
                if not video_url:
                    raise RuntimeError("Instagram needs a public video URL: set SUPABASE_URL + SUPABASE_SERVICE_KEY")
                res = instagram.publish(video_url, caption)
            row.update(status="posted", external_id=res.get("post_id") or res.get("publish_id"),
                       result=res, posted_at=dt.datetime.utcnow().isoformat() + "Z")
        except Exception as e:
            row.update(status="failed", error=str(e)[:2000])
            print(f"[{platform}] publish failed: {e}")
    if db.enabled():
        db.insert("irun_posts", row)
    print(json.dumps({"platform": platform, "product": product["id"], "status": row["status"],
                      "hook": row["hook"], "voice": vsrc, "video": video_url or video}, indent=2))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["tiktok", "instagram", "both"])
    ap.add_argument("--product")
    ap.add_argument("--mode", default=os.environ.get("IRUN_MODE", "draft"), choices=["draft", "live"])
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    if a.platform == "both":
        platforms = ["tiktok", "instagram"]
    elif a.platform:
        platforms = [a.platform]
    else:
        platforms = SCHEDULE.get(dt.datetime.utcnow().hour, ["tiktok"])

    products = load_products()
    sync_products(products)
    failed = 0
    for pf in platforms:
        try:
            row = make_one(pick_product(products, pf, a.product), pf, a.mode, a.out)
            failed += row["status"] == "failed"
        except Exception:
            traceback.print_exc()
            failed += 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
