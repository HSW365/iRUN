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
  "hashtags": ["tag", ...],            # without '#'
  "format": "video",                   # optional: "carousel" posts the beats as swipeable Instagram slides
  "angle": "the angle this script takes",          # optional: lets iRun learn which angles perform
  "experiment": "hsw365media-20261005", "variant": "A"   # optional: an A/B pair shares one experiment id
}
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


def take(account, platform, product_ids):
    """Oldest valid queued item for this account and platform. Returns (path, item, script) or None."""
    for path in sorted(glob.glob(os.path.join(QUEUE, "*.json"))):
        try:
            with open(path) as f:
                item = json.load(f)
        except Exception as e:
            print(f"[queue] unreadable {os.path.basename(path)}: {e}")
            continue
        if item.get("account", "hsw365media") != account:
            continue
        if item.get("platform", "any") not in ("any", platform):
            continue
        if item.get("product") not in product_ids:
            print(f"[queue] {os.path.basename(path)}: unknown product {item.get('product')!r} for @{account}; skipping")
            continue
        try:
            return path, item, _clean(item)
        except ValueError as e:
            print(f"[queue] {os.path.basename(path)}: {e}; skipping")
    return None


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
