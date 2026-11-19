"""Daily app promo: every post promotes ONE real capability of ONE HSW365 app.

  python engine/daily.py --count 3            # build today's ads, post them to Instagram (needs IRUN_MODE=live + IG secrets)
  python engine/daily.py --count 3 --dry      # print what would be made, render nothing
  python engine/daily.py --app calltwin --cap alerts --no-post --out out/   # one ad, no posting

How it picks:
  * apps rotate through config/daily.json "apps" (round robin, cursor in config/daily_state.json)
  * inside an app the capability that was promoted longest ago goes next, so every feature gets its day
  * the layout (browser, phone, split, stat, stack) never repeats back to back (engine/showcase.py)
  * the narrator voice never repeats back to back and is never the same voice as the last ad
  * the end card QR goes straight to the app's sign-up
State only advances after an ad posted (or built, with --no-post), so a failed ad is retried next slot.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
CAPS = os.path.join(ROOT, "config", "capabilities.json")
CFG = os.path.join(ROOT, "config", "daily.json")
STATE = os.path.join(ROOT, "config", "daily_state.json")

# Narrator pool: distinct Microsoft neural voices (free, no key). Mixed accents and ages so no two ads in a row sound alike.
VOICES = [
    "en-US-AndrewMultilingualNeural", "en-US-GuyNeural", "en-GB-RyanNeural", "en-US-BrianMultilingualNeural",
    "en-AU-WilliamMultilingualNeural", "en-US-AriaNeural", "en-US-ChristopherNeural", "en-GB-SoniaNeural",
    "en-US-EricNeural", "en-US-JennyNeural", "en-IE-ConnorNeural", "en-US-AvaMultilingualNeural",
]
BRAND_TAGS = ["hsw365", "hsw365media", "turnnegativeintopositive"]


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def pick(state, cfg, apps, force_app=None, force_cap=None, skip=()):
    """Return (app_id, cap) for the next ad."""
    order = [a for a in cfg["apps"] if a in apps]
    if force_app:
        app_id = force_app
    else:
        cur = state.get("cursor", 0)
        app_id = None
        for i in range(len(order)):
            cand = order[(cur + i) % len(order)]
            if cand not in skip:
                app_id = cand
                break
        if app_id is None:
            raise SystemExit("no app left to pick")
    caps = apps[app_id]["caps"]
    used = state.get("used", {}).get(app_id, [])  # oldest first
    if force_cap:
        cap = next((c for c in caps if c["id"] == force_cap), None)
        if not cap:
            raise SystemExit(f"{app_id} has no capability '{force_cap}'. Choose from: {', '.join(c['id'] for c in caps)}")
    else:
        fresh = [c for c in caps if c["id"] not in used]
        if fresh:
            cap = fresh[0]
        else:  # everything has had a turn: the one promoted longest ago goes again
            cap = next(c for c in caps if c["id"] == used[0]) if used else caps[0]
    return app_id, cap


def compose(app_id, app, cap):
    """Build the showcase app spec for today's capability: headline = this capability, feature row = it + two more."""
    caps = app["caps"]
    i = next(k for k, c in enumerate(caps) if c["id"] == cap["id"])
    others = [caps[(i + 1 + k) % len(caps)] for k in range(len(caps) - 1)][:2]
    feats = [cap["feature"]] + [c["feature"] for c in others]
    while len(feats) < 3:  # an app with fewer than 3 capabilities pads from the first ones
        feats.append(caps[len(feats) % len(caps)]["feature"])
    spec = {
        "name": app["name"], "accent": app["accent"], "layout": app.get("layout"), "url": app["url"],
        "signup": app.get("signup") or app["url"], "h1": cap["h1"], "h2": cap["h2"], "sub": cap["sub"],
        "stat": cap.get("stat", app["name"]), "statLabel": cap.get("statLabel", ""), "features": feats,
        "cta": app["cta"], "vo": [cap["hook"], cap["vo"], app["cta_vo"]],
    }
    return spec


def caption(app, cap):
    tags = BRAND_TAGS + app.get("tags", [])
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append("#" + t)
    lines = [f"{cap['h1']} {cap['h2']}", "", cap["sub"], "", f"{app['cta']}: scan the QR in the video.", f"{app['name']} by HSW365 Media."]
    if app.get("disclaimer"):
        lines += ["", app["disclaimer"]]
    lines += ["", " ".join(out)]
    return "\n".join(lines)


def next_voice(state, idx):
    last = state.get("voices", [])[-4:]
    pool = [v for v in VOICES if v not in last] or VOICES
    return pool[(dt.date.today().toordinal() + idx) % len(pool)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=None, help="ads to make (default: per_day in config/daily.json)")
    ap.add_argument("--app")
    ap.add_argument("--cap")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "daily"))
    ap.add_argument("--dry", action="store_true", help="print the plan, render nothing")
    ap.add_argument("--no-post", action="store_true", help="render only")
    ap.add_argument("--account", default=None)
    a = ap.parse_args()

    cfg = load(CFG, {})
    apps = load(CAPS, {}).get("apps", {})
    cfg["apps"] = [x for x in cfg.get("apps", list(apps)) if x in apps]
    if not cfg["apps"]:
        sys.exit("config/daily.json lists no apps that exist in config/capabilities.json")
    count = a.count or cfg.get("per_day", 3)
    account = a.account or cfg.get("account", "hoodstar365")
    state = load(STATE, {"cursor": 0, "used": {}, "voices": [], "log": []})
    os.makedirs(a.out, exist_ok=True)

    made, failed, skip = 0, 0, set()
    for n in range(1 if (a.app or a.cap) else count):
        app_id, cap = pick(state, cfg, apps, a.app, a.cap, skip)
        app = apps[app_id]
        spec = compose(app_id, app, cap)
        voice = next_voice(state, n)
        cap_text = caption(app, cap)
        stamp = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).strftime("%Y%m%d-%H%M")
        out = os.path.join(a.out, f"{app_id}-{cap['id']}-{stamp}.mp4")
        print(f"[daily] {n + 1}/{count}: {app['name']} / {cap['id']}  voice={voice}")
        if a.dry:
            print(json.dumps({"headline": f"{spec['h1']} {spec['h2']}", "features": spec["features"], "vo": spec["vo"],
                              "signup": spec["signup"]}, indent=1))
            print(cap_text)
            print("-" * 60)
        else:
            import showcase  # heavy imports (numpy, playwright) only when actually rendering
            showcase.VOICE = voice
            try:
                showcase.build(app_id, out, app=spec)
            except Exception as e:
                print(f"[daily] build failed for {app_id}/{cap['id']}: {e}")
                failed += 1
                skip.add(app_id)
                continue
            if not os.path.exists(out) or os.path.getsize(out) == 0:
                print(f"[daily] no video for {app_id}/{cap['id']}")
                failed += 1
                skip.add(app_id)
                continue
            if not a.no_post:
                r = subprocess.run([sys.executable, os.path.join(ROOT, "engine", "run.py"), "--account", account,
                                    "--platform", "instagram", "--mode", os.environ.get("IRUN_MODE", "live"),
                                    "--video", out, "--caption", cap_text])
                if r.returncode != 0:
                    print(f"[daily] post failed for {app_id}/{cap['id']}")
                    failed += 1
                    skip.add(app_id)
                    continue
        if a.dry:
            skip.add(app_id)  # dry runs don't advance state, so walk forward manually to show the next apps
            continue
        # advance state only for ads that were built/posted
        used = state.setdefault("used", {}).setdefault(app_id, [])
        if cap["id"] in used:
            used.remove(cap["id"])
        used.append(cap["id"])
        state["used"][app_id] = used[-len(app["caps"]):]
        if not (a.app or a.cap):
            state["cursor"] = (cfg["apps"].index(app_id) + 1) % len(cfg["apps"])
        state["voices"] = (state.get("voices", []) + [voice])[-8:]
        state.setdefault("log", []).append({"at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes") + "Z", "app": app_id,
                                            "cap": cap["id"], "voice": voice, "posted": not a.no_post})
        state["log"] = state["log"][-60:]
        save(STATE, state)
        made += 1

    print(f"[daily] done: {made} made, {failed} failed")
    sys.exit(1 if (failed and not made) else 0)


if __name__ == "__main__":
    main()
