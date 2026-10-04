"""iRun growth engine: the jobs that run around posting.

  python engine/growth.py scan --url hsw365.co [--handle hsw365.co]   # store URL -> brand profile + account + plan
  python engine/growth.py daily                                      # numbers -> A/B results -> competitors -> ads -> plan
  python engine/growth.py plan | insights | competitors | ads        # one job on its own
  python engine/growth.py fill --days 3                              # write the plan's next scripts into the queue
Add --account ID to any job to limit it to one account.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import accounts  # noqa: E402
import ads  # noqa: E402
import competitors  # noqa: E402
import content_queue  # noqa: E402
import insights  # noqa: E402
import planner  # noqa: E402
import store_scan  # noqa: E402
import writer  # noqa: E402


def _accounts(only=None, include_paused=False):
    accts = [a for a in accounts.load() if (a["enabled"] or include_paused) and (not only or a["id"] == only)]
    if only and not accts:
        sys.exit(f"No account '{only}' in config/accounts.json")
    return accts


def do_scan(url, handle=None):
    result = store_scan.scan(url, handle)
    state = store_scan.save(result)
    acct, an = result["account"], result["analysis"]
    planner.refresh(acct if state == "added" else accounts.get(acct["id"]))
    cat = an["catalog"]
    print(json.dumps({"account": acct["id"], "brand": an["brand"], "state": state, "products": cat["products"],
                      "price": cat["price"], "types": list(cat["types"])[:6], "profile_source": an["profile_source"],
                      "subjects": [s["name"] for s in an["subjects"]]}, indent=2))
    if state == "added":
        print(f"Added @{acct['id']} to config/accounts.json as paused. Read content/intel/{acct['id']}-store.json, "
              'fix anything the store got wrong, then set "enabled": true.')
    else:
        print(f"@{acct['id']} already exists: its products were left as written. Analysis and plan refreshed.")


def do_plan(accts):
    for a in accts:
        plan = planner.refresh(a, weights=insights.load(a["id"]).get("weights"))
        print(f"[plan] @{a['id']}: {plan['start']} to {plan['end']}, {len(plan['slots'])} slots")


def do_fill(accts, days):
    """Write scripts for the next `days` days of each plan into content/queue/ (needs ANTHROPIC_API_KEY)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("fill needs ANTHROPIC_API_KEY")
    import run  # cta_for / recent_hooks
    today = dt.datetime.utcnow().date()
    last = (today + dt.timedelta(days=days - 1)).isoformat()
    for a in accts:
        plan = planner.load(a["id"]) or planner.refresh(a, weights=insights.load(a["id"]).get("weights"))
        waiting = content_queue.counts().get(a["id"], 0)
        slots = [s for s in plan["slots"] if today.isoformat() <= s["date"] <= last][waiting:]
        hooks, wins, n = {}, insights.load(a["id"]).get("winning_hooks") or (), 0
        for s in slots:
            product = next((p for p in a["products"] if p["id"] == s["product"]), None)
            if not product:
                continue
            avoid = hooks.setdefault(product["id"], run.recent_hooks(a["id"], product["id"]))
            try:
                script = writer.write_script(product, s["angle"], s["platform"], run.cta_for(a, product, s["platform"])[0],
                                             avoid, voice=a.get("voice"), focus=s["focus"], winning_hooks=wins, fmt=s["format"])
            except Exception as e:
                print(f"[fill] @{a['id']} {s['date']} {s['platform']}: {e}")
                continue
            avoid.insert(0, script["beats"][0])
            name = f"{s['date'].replace('-', '')}-{s['hour_utc']:02d}-{a['id']}-{product['id']}-{s['platform']}.json"
            item = {"account": a["id"], "product": product["id"], "platform": s["platform"], **script,
                    "format": s["format"], "angle": s["angle"], "experiment": s["experiment"], "variant": s["variant"]}
            with open(os.path.join(content_queue.QUEUE, name), "w") as f:
                json.dump(item, f, indent=2)
            n += 1
        print(f"[fill] @{a['id']}: wrote {n} scripts")


def _safe(label, fn):
    try:
        return fn()
    except Exception as e:  # one job failing must not stop the others
        print(f"[{label}] failed: {e}")
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", choices=["scan", "daily", "plan", "insights", "competitors", "ads", "fill"])
    ap.add_argument("--url")
    ap.add_argument("--handle")
    ap.add_argument("--account")
    ap.add_argument("--days", type=int, default=3)
    a = ap.parse_args()

    if a.job == "scan":
        if not a.url:
            sys.exit("scan needs --url")
        return do_scan(a.url, a.handle)
    accts = _accounts(a.account)
    if a.job in ("daily", "insights"):
        _safe("insights", lambda: insights.pull(accts))
        _safe("insights", lambda: insights.report(accts))
    if a.job in ("daily", "competitors"):
        for acct in accts:
            _safe("competitors", lambda: competitors.run(acct))
    if a.job in ("daily", "ads"):
        for acct in accts:
            _safe("ads", lambda: ads.run(acct))
    if a.job in ("daily", "plan"):
        do_plan(accts)
    if a.job == "fill":
        do_fill(accts, a.days)


if __name__ == "__main__":
    main()
