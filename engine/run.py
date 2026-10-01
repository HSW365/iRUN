"""iRun engine: for each account -> pick product -> script (queue or writer) -> voice -> render -> upload
-> publish (live mode, when that account's login is connected) -> log.

Usage:
  python engine/run.py                                   # schedule slot for the current UTC hour, all enabled accounts
  python engine/run.py --platform tiktok --account hoodstar365 --product speaking --mode draft
Env IRUN_MODE=draft|live (default draft: renders + stores, never posts).
Scripts come from content/queue/ first (see engine/content_queue.py). If the queue has nothing for a slot and
ANTHROPIC_API_KEY is set, Claude writes one on the spot. With neither, that slot is skipped and logged.
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
import accounts  # noqa: E402
import content_queue  # noqa: E402
import db  # noqa: E402
import render  # noqa: E402
import voice  # noqa: E402
import writer  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
# UTC hour -> platforms. 4 TikTok + 2 Instagram per account per day (8am, 11am, 2pm, 6pm ET during EDT).
# GitHub often starts scheduled runs late, so a run belongs to the nearest slot at or before its start hour.
SCHEDULE = {12: ["tiktok"], 15: ["tiktok", "instagram"], 18: ["tiktok"], 22: ["tiktok", "instagram"]}


def slot_platforms(hour):
    for h in sorted(SCHEDULE, reverse=True):
        if hour >= h:
            return SCHEDULE[h]
    return SCHEDULE[max(SCHEDULE)]  # just after midnight UTC = the previous evening's late slot


def sync_products(accts):
    if not db.enabled():
        return
    for a in accts:
        if a["id"] != accounts.MAIN:  # the IG lead bot reads irun_products; it only runs on the main account today
            continue
        for p in a["products"]:
            if not p.get("link"):
                continue
            db.insert("irun_products", {"id": p["id"], "name": p["name"], "keyword": p["keyword"].upper(),
                                        "link": p["link"], "pitch": p["pitch"], "active": True}, upsert_on="id")


def pick_product(acct, platform, forced=None):
    products = acct["products"]
    if forced:
        return next(p for p in products if p["id"] == forced)
    if db.enabled():
        rows = db.select("irun_posts", f"account=eq.{acct['id']}&platform=eq.{platform}"
                                       "&select=product_id,created_at&order=created_at.desc&limit=50")
        recent = [r["product_id"] for r in rows]
        never = [p for p in products if p["id"] not in recent]
        if never:
            return random.choice(never)
        return max(products, key=lambda p: recent.index(p["id"]))  # least recently used
    now = dt.datetime.utcnow()
    return products[(now.timetuple().tm_yday * 7 + now.hour) % len(products)]


def recent_hooks(account_id, product_id):
    if not db.enabled():
        return []
    rows = db.select("irun_posts", f"account=eq.{account_id}&product_id=eq.{product_id}"
                                   "&select=hook&order=created_at.desc&limit=8")
    return [r["hook"] for r in rows if r.get("hook")]


def cta_for(acct, product, platform):
    """(spoken, (screen line 1, screen line 2), caption line)."""
    c = product.get("cta")
    if c:
        return c["spoken"], tuple(c["screen"]), c["caption"]
    kw, h = product["keyword"].upper(), acct["handle"]
    if acct.get("lead_bot"):
        if platform == "instagram":
            return (f"Comment {kw} and I'll DM you the link", (f"COMMENT \"{kw}\"", f"OR DM \"{kw}\" TO @{h.upper()}"),
                    f"Comment {kw} and the link lands in your DMs.")
        return (f"DM {kw} to @{h} on Instagram for the link", (f"DM \"{kw}\"", f"TO @{h.upper()} ON INSTAGRAM"),
                f"DM {kw} to @{h} on Instagram and the link comes straight to you. Link in bio too.")
    return ("Link in bio", ("LINK IN BIO", f"@{h.upper()}"), "Link in bio.")


def make_one(acct, product, platform, mode, outdir, queued=None):
    spoken_cta, screen_cta, caption_cta = cta_for(acct, product, platform)
    if queued:
        qpath, qitem, script = queued
        source = f"queue:{os.path.basename(qpath)}"
    else:
        angle = random.choice(product.get("angles") or [product["pitch"]])
        script = writer.write_script(product, angle, platform, spoken_cta,
                                     recent_hooks(acct["id"], product["id"]), voice=acct.get("voice"))
        source = "writer"
    caption = script["caption"]
    if caption_cta.lower()[:20] not in caption.lower():
        caption = f"{caption}\n\n{caption_cta}"
    if script["hashtags"]:
        caption += "\n\n" + " ".join("#" + t for t in script["hashtags"])

    os.makedirs(outdir, exist_ok=True)
    stamp = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    slug = f"{stamp}-{acct['id']}-{platform}-{product['id']}"
    work = tempfile.mkdtemp(prefix="irun-")
    audio, alen, vsrc = voice.speak(" ".join(script["beats"]), os.path.join(work, "vo.mp3"))
    video = os.path.join(outdir, f"{slug}.mp4")
    render.render(script["beats"], script["emphasis"], audio, alen, product, work, video, cta=screen_cta,
                  brand=acct["brand"], handle=acct["handle"])
    with open(os.path.join(outdir, f"{slug}.txt"), "w") as f:
        f.write(caption + "\n\n---\n" + "\n".join(script["beats"]))

    row = {"account": acct["id"], "platform": platform, "product_id": product["id"], "hook": script["beats"][0],
           "caption": caption, "script": script["beats"], "voice": vsrc, "status": "draft", "mode": mode}
    video_url = None
    if db.enabled():
        video_url = db.upload_public(video, f"{slug}.mp4")
        row["video_url"] = video_url

    ok, why = accounts.connected(acct["id"], platform)
    attempted = False
    if mode == "live" and not ok:
        row["error"] = f"not posted: {why}"
        print(f"[{acct['id']}/{platform}] draft only: {why}")
    elif mode == "live":
        attempted = True
        try:
            if platform == "tiktok":
                import tiktok
                res = tiktok.publish(video, caption, account=acct["id"])
            else:
                import instagram
                res = instagram.publish(video_url, caption, account=acct["id"])
            row.update(status="posted", external_id=res.get("post_id") or res.get("publish_id"),
                       result=res, posted_at=dt.datetime.utcnow().isoformat() + "Z")
        except Exception as e:
            row.update(status="failed", error=str(e)[:2000])
            print(f"[{acct['id']}/{platform}] publish failed: {e}")
    if queued and attempted:
        content_queue.finish(qpath, qitem, row)
    if db.enabled():
        db.insert("irun_posts", row)
    print(json.dumps({"account": acct["id"], "platform": platform, "product": product["id"], "status": row["status"],
                      "source": source, "hook": row["hook"], "voice": vsrc, "video": video_url or video}, indent=2))
    return row


def preflight(accts, mode):
    def has(k):
        return "set" if os.environ.get(k) else "MISSING"
    print("=== iRun preflight ===")
    print(f"mode: {mode}")
    for k in ["SUPABASE_SERVICE_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "TIKTOK_CLIENT_KEY",
              "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN", "IG_ACCESS_TOKEN"]:
        print(f"  {k:<22} {has(k)}")
    q = content_queue.counts()
    for a in accts:
        state = "enabled" if a["enabled"] else "paused"
        links = ", ".join(f"{p}: {accounts.connected(a['id'], p)[1]}" for p in a["platforms"])
        print(f"  @{a['id']:<14} {state:<8} queue={q.get(a['id'], 0):<3} {links}")
    print("======================")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["tiktok", "instagram", "both"])
    ap.add_argument("--account", help="only this account id")
    ap.add_argument("--product")
    ap.add_argument("--mode", default=os.environ.get("IRUN_MODE", "draft"), choices=["draft", "live"])
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    accts = [x for x in accounts.load() if x["enabled"] and (not a.account or x["id"] == a.account)]
    if a.account and not accts:
        sys.exit(f"No enabled account '{a.account}' in config/accounts.json")
    preflight(accts, a.mode)
    sync_products(accts)

    if a.platform == "both":
        wanted = ["tiktok", "instagram"]
    elif a.platform:
        wanted = [a.platform]
    else:
        wanted = slot_platforms(dt.datetime.utcnow().hour)

    failed, made, skipped = 0, 0, 0
    has_writer = bool(os.environ.get("ANTHROPIC_API_KEY"))
    for acct in accts:
        for pf in [p for p in wanted if p in acct["platforms"]]:
            try:
                ids = [p["id"] for p in acct["products"]]
                queued = None if a.product else content_queue.take(acct["id"], pf, ids)
                if queued:
                    product = next(p for p in acct["products"] if p["id"] == queued[1]["product"])
                elif has_writer:
                    product = pick_product(acct, pf, a.product)
                else:
                    skipped += 1
                    print(f"[{acct['id']}/{pf}] skipped: queue is empty and no ANTHROPIC_API_KEY to write a script")
                    continue
                row = make_one(acct, product, pf, a.mode, a.out, queued)
                made += 1
                failed += row["status"] == "failed"
            except Exception:
                traceback.print_exc()
                failed += 1
    print(f"done: {made} made, {skipped} skipped (no script), {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
