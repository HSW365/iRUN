"""iRun App Growth: scripts, videos and ads that get an app downloaded.

You made the app. Now it needs downloads. The owner signs up on appgrowth.html with the app's App Store link (or its
name). Every day at the plan's posting hour iRun's growth team works that app:

  scout     reads the app's public App Store listing (iTunes lookup API, no key): name, pitch, features, rating, icon
  writer    writes the day's batch of short-form scripts: hook, a short acted micro-drama scene, payoff, caption
            (engine/llm.py; only facts from the listing go into a script, no invented stats or reviews)
  studio    renders the day's ad (engine/showcase.py) with a narrator and an end-card QR straight to the download page
  poster    posts it to the app's Instagram when connected (engine/run.py), draft mode renders only
  ceo       the nightly Operator review reads what posted and plans tomorrow

Every script, caption and ad is saved to content/appgrowth/<company>/<day>/ so the owner can use them anywhere.
One ad a day = 1 credit. No cut of downloads or revenue.

  python engine/appgrowth.py --check "Notion"                 look an app up
  python engine/appgrowth.py --scripts "https://apps.apple.com/us/app/notion/id1232780281"   scripts only, no video
  python engine/appgrowth.py --company acme --now             one app, right now
  python engine/appgrowth.py                                  every App Growth app whose posting hour is now
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import traceback

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

UA = {"User-Agent": "Mozilla/5.0 (compatible; iRunAppGrowth/1.0; +https://hsw365.github.io/iRUN/appgrowth.html)"}
ACCENTS = [["#5cff9d", "#22d3ee"], ["#a855f7", "#22d3ee"], ["#fbbf24", "#ef4444"], ["#ff2d78", "#a855f7"],
           ["#34d399", "#3b82f6"], ["#22d3ee", "#3b82f6"]]
LAYOUTS = ["browser", "phone", "split", "stat", "stack"]


def app_id(text):
    """App Store numeric id from a link like .../id1232780281, or None."""
    m = re.search(r"/id(\d{6,})", text or "") or re.fullmatch(r"\s*(\d{6,})\s*", text or "")
    return m.group(1) if m else None


def lookup(q):
    """Public App Store listing for a link, numeric id or app name. None when nothing matches."""
    q = (q or "").strip()
    if not q:
        return None
    i = app_id(q)
    if i:
        r = requests.get("https://itunes.apple.com/lookup", params={"id": i}, headers=UA, timeout=30)
    else:
        r = requests.get("https://itunes.apple.com/search", headers=UA, timeout=30,
                         params={"term": q, "entity": "software", "limit": 1})
    rows = r.json().get("results", []) if r.status_code == 200 else []
    if not rows:
        return None
    a = rows[0]
    return {
        "id": str(a.get("trackId")), "name": (a.get("trackName") or "").split(" - ")[0].split(": ")[0].strip(),
        "full_name": a.get("trackName"), "seller": a.get("sellerName"), "genre": a.get("primaryGenreName"),
        "url": a.get("trackViewUrl", "").split("?")[0], "icon": a.get("artworkUrl512"),
        "price": a.get("formattedPrice"), "rating": a.get("averageUserRating"), "ratings": a.get("userRatingCount"),
        "description": (a.get("description") or "")[:2500], "notes": (a.get("releaseNotes") or "")[:600],
        "shots": (a.get("screenshotUrls") or [])[:5],
    }


SYSTEM = """You write short-form video scripts that get a mobile app downloaded. You work from the app's real listing only.
Rules: never invent statistics, reviews, awards, user counts or features that are not in the listing. Every script is a
tiny acted scene (micro-drama: a person with a real problem, a turn, the app solving it), not a feature list. First two
seconds must stop the scroll. Plain spoken English a narrator can say in one breath per line. Return JSON only."""


def write(app, n=3, recent=None):
    """n scripts + the day's ad spec for one app. Needs ANTHROPIC_API_KEY."""
    import llm
    user = f"""APP LISTING
name: {app['name']}  | category: {app['genre']} | price: {app['price']} | rating: {app.get('rating')} ({app.get('ratings')} ratings)
description: {app['description']}
latest release notes: {app['notes']}

Already used recently (do not repeat these angles): {json.dumps(recent or [])}

Return JSON:
{{"scripts":[{{"angle":"the one problem/benefit this script is about","hook":"first 2s line, on screen and spoken",
 "scene":["3-5 short beats of the acted scene, each one visual action or line"],"payoff":"the line where the app fixes it",
 "cta":"short download line","caption":"search-friendly caption, first line is what a person types in the search bar",
 "hashtags":["3-5 relevant tags without #"]}}]  (exactly {n}),
 "ad":{{"h1":"white headline line (max 3 words)","h2":"accent headline line (max 4 words)","sub":"one sentence from the listing",
 "stat":"short stat-like label that is TRUE from the listing (e.g. the rating, price or 'Free')","statLabel":"what the stat means",
 "features":[["title","detail"],["title","detail"],["title","detail"]],"hook":"narrator opening line","vo":"narrator line about the app",
 "cta":"button text","cta_vo":"narrator close"}}}}"""
    return llm.ask_json(SYSTEM, user, max_tokens=3500)


def spec_for(app, ad, seed):
    return {
        "name": app["name"], "accent": ACCENTS[seed % len(ACCENTS)], "layout": LAYOUTS[seed % len(LAYOUTS)],
        "url": app["url"], "signup": app["url"], "h1": ad["h1"], "h2": ad["h2"], "sub": ad["sub"],
        "stat": ad.get("stat") or app["name"], "statLabel": ad.get("statLabel", ""),
        "features": ad["features"][:3], "cta": ad.get("cta") or "Download free",
        "vo": [ad["hook"], ad["vo"], ad.get("cta_vo") or "Scan the code and download it now."],
    }


def caption_of(app, script):
    tags = " ".join("#" + t.strip("#") for t in (script.get("hashtags") or [])[:5])
    return f"{script['caption']}\n\n{script['cta']}: scan the QR in the video.\n{app['name']} on the App Store.\n\n{tags}\n#appgrowth"


def make(app, day, seed=0, post_to=None, mode="draft", company=None):
    """Scripts + one rendered ad for today. Returns the result dict."""
    out_dir = os.path.join(ROOT, "content", "appgrowth", company or app["id"], day)
    os.makedirs(out_dir, exist_ok=True)
    plan = write(app, 3, None)
    with open(os.path.join(out_dir, "scripts.json"), "w") as f:
        json.dump({"app": {k: app[k] for k in ("id", "name", "url", "genre")}, **plan}, f, indent=2)
    import showcase
    spec = spec_for(app, plan["ad"], seed)
    video, layout = showcase.build(f"app-{app['id']}", os.path.join(out_dir, "ad.mp4"), layout=spec["layout"], app=spec)
    cap = caption_of(app, plan["scripts"][0])
    with open(os.path.join(out_dir, "caption.txt"), "w") as f:
        f.write(cap)
    posted = {}
    for pf in post_to or []:
        r = subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "--account", company, "--platform", pf,
                            "--video", video, "--caption", cap, "--mode", mode])
        posted[pf] = "posted" if r.returncode == 0 else "failed"
    return {"video": video, "caption": cap, "scripts": plan["scripts"], "layout": layout, "posted": posted, "dir": out_dir}


def store_of(c):
    prof = c.get("profile") or {}
    return (prof.get("app") or {}).get("id") and prof["app"] or lookup(c.get("source_url") or c.get("name"))


def eligible(c):
    import companies
    return bool(companies.plan_of(c).get("app_ads")) or c.get("plan") == "comp"


def work(c, mode, force=False):
    import accounts
    import companies
    plan = companies.plan_of(c)
    today = dt.datetime.utcnow().date().isoformat()
    prof = dict(c.get("profile") or {})
    state = dict(prof.get("app") or {})
    if not force and (dt.datetime.utcnow().hour < plan.get("app_hour", 16) or state.get("last_day") == today):
        return "not this hour"
    app = state if state.get("id") else lookup(c.get("source_url") or c.get("name"))
    if not app:
        companies.log(c["id"], "appgrowth", "no App Store listing found. Reply with your App Store link to start.")
        return "no app"
    pfs = [p for p in ("instagram", "tiktok") if accounts.connected(c["id"], p)[0]]
    if not pfs and mode == "live":
        companies.log(c["id"], "appgrowth", "today's ad is waiting: connect Instagram on your live page to start posting")
    if not companies.spend(c["id"], companies.plans()["costs"]["video"], f"app ad: {app['name']}"[:120]):
        return "out of credits"
    try:
        res = make(app, today, seed=int(state.get("count") or 0), post_to=pfs, mode=mode, company=c["id"])
    except Exception as e:
        traceback.print_exc()
        companies.refund(c["id"], companies.plans()["costs"]["video"], f"app ad failed: {app['name']}"[:120])
        companies.log(c["id"], "appgrowth", f"ad for {app['name']} failed, credit refunded: {e}"[:300])
        return "failed"
    state.update(app, last_day=today, count=int(state.get("count") or 0) + 1,
                 angles=((state.get("angles") or []) + [s["angle"] for s in res["scripts"]])[-30:])
    prof["app"] = state
    companies.save(c["id"], profile=prof)
    companies.log(c["id"], "appgrowth", f"{len(res['scripts'])} scripts + 1 ad for {app['name']}, QR to the download page",
                  {"platforms": res["posted"], "dir": os.path.relpath(res["dir"], ROOT)})
    companies.remember(c["id"], "post", f"{today}: app ad + {len(res['scripts'])} scripts for {app['name']} -> {res['posted']}")
    return f"{app['name']}: {res['posted'] or 'rendered'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company")
    ap.add_argument("--now", action="store_true", help="ignore the posting hour / once-a-day guard")
    ap.add_argument("--check", metavar="APP", help="look an app up and exit")
    ap.add_argument("--scripts", metavar="APP", help="print today's scripts for an app and exit (no video)")
    ap.add_argument("--mode", default=os.environ.get("IRUN_MODE", "draft"), choices=["draft", "live"])
    a = ap.parse_args()
    if a.check or a.scripts:
        app = lookup(a.check or a.scripts)
        if not app:
            sys.exit("no App Store listing found")
        if a.check:
            print(json.dumps({k: app[k] for k in ("id", "name", "genre", "price", "rating", "url")}, indent=2))
        else:
            print(json.dumps(write(app), indent=2))
        return
    import companies
    import db
    if not db.enabled():
        sys.exit("App Growth needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
    print(f"=== iRun App Growth === mode={a.mode}")
    for c in companies.all_companies("active"):
        if (a.company and c["id"] != a.company) or not eligible(c):
            continue
        try:
            print(f"[{c['id']}] {work(c, a.mode, a.now)}")
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
