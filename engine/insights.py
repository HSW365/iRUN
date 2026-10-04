"""Performance: pull each post's numbers, score them, settle A/B hook tests and tell the planner what is working.

Score = views + 5 x likes + 10 x comments + 15 x shares + 15 x saves. It is a ranking number, not a prediction.
An A/B test is settled once both posts are at least 48 hours old. With under 100 combined views it is marked
"not enough data" instead of naming a winner.

Writes content/intel/<account>-performance.json (read by planner.py, writer context and the dashboard).
"""
import datetime as dt
import json
import os

import db

ROOT = os.path.join(os.path.dirname(__file__), "..")
INTEL = os.path.join(ROOT, "content", "intel")
SETTLE_HOURS = 48
MIN_TEST_VIEWS = 100
WINDOW_DAYS = 45


def score(m):
    return (int(m.get("views") or 0) + 5 * int(m.get("likes") or 0) + 10 * int(m.get("comments") or 0)
            + 15 * int(m.get("shares") or 0) + 15 * int(m.get("saves") or 0))


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _when(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _posted_rows():
    since = (_now() - dt.timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return db.select("irun_posts", f"status=eq.posted&posted_at=gte.{since}&order=posted_at.desc&limit=1000"
                                   "&select=id,account,platform,product_id,angle,format,experiment,variant,hook,"
                                   "external_id,result,posted_at,metrics,score")


def pull(accts):
    """Refresh metrics on every recent post. Returns how many were updated."""
    if not db.enabled():
        print("[insights] no SUPABASE_SERVICE_KEY: nothing to measure")
        return 0
    ids = {a["id"] for a in accts}
    rows = [r for r in _posted_rows() if r["account"] in ids and r.get("external_id")]
    updated = 0
    for acct_id in sorted({r["account"] for r in rows}):
        mine = [r for r in rows if r["account"] == acct_id]
        got = {}
        ig = [r for r in mine if r["platform"] == "instagram"]
        if ig:
            try:
                import instagram
                tok = instagram.access_token(acct_id)
                for r in ig:
                    try:
                        got[r["id"]] = instagram.metrics(r["external_id"], tok, carousel=r.get("format") == "carousel")
                    except Exception as e:
                        print(f"[insights] @{acct_id} instagram post {r['external_id']}: {e}")
            except Exception as e:
                print(f"[insights] @{acct_id} instagram: {e}")
        tt = {str((r.get("result") or {}).get("post_id")): r for r in mine
              if r["platform"] == "tiktok" and (r.get("result") or {}).get("post_id")}
        if tt:
            try:
                import tiktok
                tok = tiktok.access_token(acct_id)
                vids = list(tt)
                for i in range(0, len(vids), 20):
                    for vid, m in tiktok.metrics(vids[i:i + 20], tok).items():
                        if vid in tt:
                            got[tt[vid]["id"]] = m
            except Exception as e:
                print(f"[insights] @{acct_id} tiktok: {e}")
        for row_id, m in got.items():
            db.update("irun_posts", {"id": row_id}, {"metrics": m, "score": score(m),
                                                     "metrics_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ")})
            updated += 1
    print(f"[insights] refreshed {updated} posts")
    return updated


def _avg(nums):
    nums = list(nums)
    return round(sum(nums) / len(nums), 1) if nums else 0


def experiments(rows, now=None):
    now = now or _now()
    tests = {}
    for r in rows:
        if r.get("experiment") and r.get("variant") in ("A", "B"):
            tests.setdefault(r["experiment"], {})[r["variant"]] = r
    out = []
    for name, pair in sorted(tests.items(), reverse=True):
        a, b = pair.get("A"), pair.get("B")
        item = {"experiment": name, "product": (a or b).get("product_id"), "angle": (a or b).get("angle"),
                "A": _brief(a), "B": _brief(b)}
        if not (a and b):
            item["status"] = "waiting for the second post"
        elif a.get("metrics") is None or b.get("metrics") is None:
            item["status"] = "waiting for numbers"
        elif min(now - _when(a["posted_at"]), now - _when(b["posted_at"])) < dt.timedelta(hours=SETTLE_HOURS):
            item["status"] = "running"
        elif (a["metrics"].get("views") or 0) + (b["metrics"].get("views") or 0) < MIN_TEST_VIEWS:
            item["status"] = "not enough data"
        elif (a.get("score") or 0) == (b.get("score") or 0):
            item["status"] = "tie"
        else:
            item["status"] = "settled"
            item["winner"] = "A" if (a.get("score") or 0) > (b.get("score") or 0) else "B"
        out.append(item)
    return out


def _brief(r):
    if not r:
        return None
    return {"hook": r.get("hook"), "score": r.get("score"), "metrics": r.get("metrics"), "posted_at": r.get("posted_at")}


def summarize(account_id, rows, now=None):
    """rows: this account's posted rows. Returns the performance report, including planner weights."""
    measured = [r for r in rows if r.get("metrics") is not None]
    overall = _avg(r.get("score") or 0 for r in measured)

    def group(key):
        buckets = {}
        for r in measured:
            k = key(r)
            if k:
                buckets.setdefault(k, []).append(r.get("score") or 0)
        return {k: {"posts": len(v), "avg_score": _avg(v)} for k, v in buckets.items()}

    by_product = group(lambda r: r.get("product_id"))
    by_angle = group(lambda r: f"{r['product_id']}|{r['angle']}" if r.get("angle") else None)
    by_format = group(lambda r: f"{r['platform']} {r.get('format') or 'video'}")

    def weights(buckets):  # needs 2+ measured posts before it moves anything
        return {k: round(min(max(v["avg_score"] / overall, 0.5), 2.0), 2)
                for k, v in buckets.items() if v["posts"] >= 2 and overall > 0}

    tests = experiments(rows, now)
    top = sorted(measured, key=lambda r: r.get("score") or 0, reverse=True)[:10]
    winners = [t[t["winner"]]["hook"] for t in tests if t.get("winner")]
    winning_hooks = list(dict.fromkeys(winners + [r["hook"] for r in top[:5] if r.get("hook")]))[:6]
    return {
        "account": account_id, "updated_at": (now or _now()).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "posts_measured": len(measured), "posts_total": len(rows), "avg_score": overall,
        "totals": {k: sum(int((r["metrics"] or {}).get(k) or 0) for r in measured)
                   for k in ("views", "likes", "comments", "shares", "saves")},
        "by_product": by_product, "by_angle": by_angle, "by_format": by_format,
        "weights": {"products": weights(by_product), "angles": weights(by_angle)},
        "experiments": tests[:30],
        "winning_hooks": winning_hooks if measured else [],
        "top_posts": [{"platform": r["platform"], "product": r.get("product_id"), "hook": r.get("hook"),
                       "score": r.get("score"), "metrics": r.get("metrics"), "posted_at": r.get("posted_at")} for r in top],
    }


def path(account_id):
    return os.path.join(INTEL, f"{account_id}-performance.json")


def load(account_id):
    try:
        with open(path(account_id)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def report(accts):
    """Write each account's performance file from what is stored. Returns {account: report}."""
    if not db.enabled():
        return {}
    rows = _posted_rows()
    os.makedirs(INTEL, exist_ok=True)
    out = {}
    for a in accts:
        rep = summarize(a["id"], [r for r in rows if r["account"] == a["id"]])
        with open(path(a["id"]), "w") as f:
            json.dump(rep, f, indent=1)
        out[a["id"]] = rep
    return out
