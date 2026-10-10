"""Content queue: scripts written ahead of time (by the scheduled Claude writer or by hand) wait in
content/queue/*.json and iRun turns them into videos. This lets iRun run with no paid AI API key.

Queue item shape:
{
  "account": "hsw365media",            # id from config/accounts.json
  "product": "calltwin",               # product id within that account
  "platform": "any",                   # "tiktok", "instagram" or "any"
  "beats": ["hook", "...", "CTA beat with KEYWORD"],
  "emphasis": ["word", ...],           # one word per beat to highlight (optional)
  "caption": "1-3 sentences",
  "hashtags": ["tag", ...]             # without '#'
}

Faceless item shape (story-style video with AI scenes; see engine/faceless.py and config/series.json):
{
  "kind": "faceless",
  "account": "hoodstar365",
  "series": "tnip",                    # id from config/series.json
  "style": "cinematic",                # optional, id from config/styles.json (defaults to the series style)
  "title": "Your setback is the setup",
  "scenes": [{"say": "spoken line", "visual": "what the picture shows"}, ...],
  "caption": "1-3 sentences",
  "hashtags": ["tag", ...]
}
One faceless video is cross-posted to all of the account's platforms, so it has no "platform" field.
"""
import datetime as dt
import glob
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
QUEUE = os.path.join(ROOT, "content", "queue")
POSTED = os.path.join(ROOT, "content", "posted")
FAILED = os.path.join(ROOT, "content", "failed")
MAX_ATTEMPTS = 3


def _clean(item):
    beats = [re.sub(r"[^\x00-\x7F]+", "", b).strip() for b in item.get("beats", []) if str(b).strip()]
    if not 3 <= len(beats) <= 9:
        raise ValueError(f"needs 3-9 beats, got {len(beats)}")
    emph = (list(item.get("emphasis") or []) + [""] * len(beats))[: len(beats)]
    tags = [str(t).lstrip("#").replace(" ", "") for t in item.get("hashtags", [])][:6]
    return {"beats": beats, "emphasis": emph, "caption": str(item.get("caption", "")).strip(), "hashtags": tags}


def take_faceless(account, series_ids, offset=0):
    """A valid queued faceless item for this account. Returns (path, item, script) or None. offset as in take()."""
    import faceless
    found = []
    for path in sorted(glob.glob(os.path.join(QUEUE, "*.json"))):
        try:
            with open(path) as f:
                item = json.load(f)
        except Exception as e:
            print(f"[queue] unreadable {os.path.basename(path)}: {e}")
            continue
        if item.get("kind") != "faceless" or item.get("account") != account:
            continue
        if item.get("series") not in series_ids:
            print(f"[queue] {os.path.basename(path)}: unknown or paused series {item.get('series')!r} for @{account}; skipping")
            continue
        try:
            found.append((path, item, faceless.clean(item)))
        except ValueError as e:
            print(f"[queue] {os.path.basename(path)}: {e}; skipping")
        if found and not offset:
            break
    return found[offset % len(found)] if found else None


def finish_faceless(path, item, rows):
    """After a cross-post: done if any platform took it; otherwise keep for retry until MAX_ATTEMPTS runs."""
    item.setdefault("attempts", [])
    now = dt.datetime.utcnow().isoformat() + "Z"
    for row in rows:
        item["attempts"].append({"at": now, "platform": row["platform"], "status": row["status"],
                                 "error": row.get("error"), "external_id": row.get("external_id")})
    runs = len({a["at"] for a in item["attempts"]})
    if any(r["status"] == "posted" for r in rows):
        dest = POSTED
    elif runs >= MAX_ATTEMPTS:
        dest = FAILED
    else:
        with open(path, "w") as f:
            json.dump(item, f, indent=2)
        return path
    os.makedirs(dest, exist_ok=True)
    new = os.path.join(dest, os.path.basename(path))
    with open(new, "w") as f:
        json.dump(item, f, indent=2)
    os.remove(path)
    return new


def take(account, platform, product_ids, offset=0):
    """A valid queued item for this account and platform. Returns (path, item, script) or None.

    offset 0 is the oldest item, which is what live runs use: they post it and it leaves the queue.
    Draft runs never remove anything, so they pass a rotating offset. Without it every draft run
    would render the same first script again.
    """
    found = []
    for path in sorted(glob.glob(os.path.join(QUEUE, "*.json"))):
        try:
            with open(path) as f:
                item = json.load(f)
        except Exception as e:
            print(f"[queue] unreadable {os.path.basename(path)}: {e}")
            continue
        if item.get("kind", "promo") != "promo":  # faceless items are handled by take_faceless
            continue
        if item.get("account", "hsw365media") != account:
            continue
        if item.get("platform", "any") not in ("any", platform):
            continue
        if item.get("product") not in product_ids:
            print(f"[queue] {os.path.basename(path)}: unknown product {item.get('product')!r} for @{account}; skipping")
            continue
        try:
            found.append((path, item, _clean(item)))
        except ValueError as e:
            print(f"[queue] {os.path.basename(path)}: {e}; skipping")
        if found and not offset:
            break
    return found[offset % len(found)] if found else None


def finish(path, item, row):
    """Move a queue item out of the queue after a publish attempt (kept for retry until MAX_ATTEMPTS)."""
    item.setdefault("attempts", [])
    item["attempts"].append({"at": dt.datetime.utcnow().isoformat() + "Z", "platform": row["platform"],
                             "status": row["status"], "error": row.get("error"), "external_id": row.get("external_id")})
    if row["status"] == "posted":
        dest = POSTED
    elif len(item["attempts"]) >= MAX_ATTEMPTS:
        dest = FAILED
    else:
        with open(path, "w") as f:
            json.dump(item, f, indent=2)
        return path
    os.makedirs(dest, exist_ok=True)
    new = os.path.join(dest, os.path.basename(path))
    with open(new, "w") as f:
        json.dump(item, f, indent=2)
    os.remove(path)
    return new


def counts():
    out = {}
    for path in glob.glob(os.path.join(QUEUE, "*.json")):
        try:
            with open(path) as f:
                a = json.load(f).get("account", "hsw365media")
        except Exception:
            continue
        out[a] = out.get(a, 0) + 1
    return out
