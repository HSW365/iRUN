"""Competitor watch and price benchmarks.

For an account with "competitors": ["https://store-a.com", ...] in config/accounts.json, iRun reads each
competitor's public Shopify catalog once a day and records:
  - what they sell and their price range, overall and per product type
  - how the account's own store (its "store" URL) compares on price
  - what changed since the last check: new products, removed products, price changes
Only stores built on Shopify expose this feed. Others are reported as unreadable, not guessed at.
Saved to content/intel/<account>-competitors.json.
"""
import datetime as dt
import json
import os

import shopify

ROOT = os.path.join(os.path.dirname(__file__), "..")
INTEL = os.path.join(ROOT, "content", "intel")
KEEP_CHANGES = 100


def snapshot(products):
    return {str(p.get("handle") or p.get("id")): {"title": p.get("title"), "price": shopify.price(p)} for p in products}


def diff(old, new, store, when):
    """Changes between two snapshots of one store."""
    out = []
    for h, p in new.items():
        if h not in old:
            out.append({"at": when, "store": store, "change": "new product", "title": p["title"], "price": p["price"]})
        elif old[h].get("price") != p["price"] and None not in (old[h].get("price"), p["price"]):
            out.append({"at": when, "store": store, "change": "price up" if p["price"] > old[h]["price"] else "price down",
                        "title": p["title"], "from": old[h]["price"], "price": p["price"]})
    for h, p in old.items():
        if h not in new:
            out.append({"at": when, "store": store, "change": "removed", "title": p.get("title"), "price": p.get("price")})
    return out


def compare(own, theirs):
    """Own median vs a competitor's, overall and for product types both stores carry. Percent is own relative to theirs."""
    def pct(a, b):
        return round(100 * (a - b) / b) if a is not None and b else None

    out = {"overall": None, "by_type": {}}
    if own.get("price") and theirs.get("price"):
        out["overall"] = {"own_median": own["price"]["median"], "their_median": theirs["price"]["median"],
                          "own_vs_theirs_pct": pct(own["price"]["median"], theirs["price"]["median"])}
    mine = {t.lower(): v for t, v in own.get("types", {}).items()}
    for t, v in theirs.get("types", {}).items():
        m = mine.get(t.lower())
        if m and m.get("price") and v.get("price"):
            out["by_type"][t] = {"own_median": m["price"]["median"], "their_median": v["price"]["median"],
                                 "own_vs_theirs_pct": pct(m["price"]["median"], v["price"]["median"])}
    return out


def path(account_id):
    return os.path.join(INTEL, f"{account_id}-competitors.json")


def run(acct, fetch=shopify.fetch_products, now=None):
    """Returns the report (also saved), or None when the account lists no competitors."""
    urls = acct.get("competitors") or []
    if not urls:
        return None
    when = (now or dt.datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(path(acct["id"])) as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    prev_snaps = prev.get("snapshots", {})

    own = None
    if acct.get("store"):
        try:
            own = shopify.summarize(fetch(shopify.normalize(acct["store"])))
        except Exception as e:
            print(f"[competitors] @{acct['id']} own store unreadable: {e}")

    stores, snaps, changes = [], {}, []
    for url in urls:
        try:
            base = shopify.normalize(url)
            products = fetch(base)
        except Exception as e:
            stores.append({"store": url, "readable": False, "error": str(e)[:200]})
            if url in prev_snaps:
                snaps[url] = prev_snaps[url]  # keep the last good snapshot so one outage doesn't flag everything as new
            continue
        cat = shopify.summarize(products)
        snap = snapshot(products)
        snaps[url] = snap
        if url in prev_snaps:
            changes += diff(prev_snaps[url], snap, shopify.host_of(base), when)
        stores.append({"store": shopify.host_of(base), "readable": True, "catalog": cat,
                       "vs_own": compare(own, cat) if own else None})

    report = {"account": acct["id"], "checked_at": when, "own": own, "stores": stores,
              "changes": (changes + prev.get("changes", []))[:KEEP_CHANGES], "snapshots": snaps}
    os.makedirs(INTEL, exist_ok=True)
    with open(path(acct["id"]), "w") as f:
        json.dump(report, f, indent=1)
    print(f"[competitors] @{acct['id']}: {sum(s['readable'] for s in stores)}/{len(stores)} stores read, "
          f"{len(changes)} changes")
    return report
