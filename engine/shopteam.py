"""iRun Shop Team: an AI marketing team for a Shopify store, about 90 cents a day.

The store owner signs up on shopteam.html with their store link and connects Instagram (TikTok too, if they want).
Every day at the plan's posting hour iRun's team works the catalog:

  catalog   reads the store's public product feed (/products.json): every live product, price, photos, variants
  director  picks the next product in rotation (new products jump the line, sold-out ones are skipped)
  studio    builds a ~19s cinematic trailer ad for it in the store's own brand (engine/shopify_ad.py):
            cold open, title slam, spec card from the product page, three slam words, payoff, end card
  closer    the end-card QR goes straight to checkout for that product (cart permalink), not the homepage
  poster    posts it to the store's Instagram (and TikTok when connected) with caption + hashtags
  ceo       the nightly Operator review (engine/ceo.py) reads what posted and plans tomorrow

One ad a day = 1 credit. No cut of sales. Only facts from the store's own product pages go into an ad.

  python engine/shopteam.py                       every Shop Team store whose posting hour is now
  python engine/shopteam.py --company acme --now  one store, right now
  python engine/shopteam.py --check acme.com      is this a Shopify store? how many products?
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import traceback

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import accounts  # noqa: E402
import companies  # noqa: E402
import db  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; iRunShopTeam/1.0; +https://hsw365.github.io/iRUN/shopteam.html)"}


def domain(url):
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u).split("/")[0].split("?")[0]
    return u.strip(".")


def catalog(store):
    """Live, purchasable products from a Shopify store's public feed. [] when it isn't a Shopify store."""
    out, page = [], 1
    while page <= 4:
        r = requests.get(f"https://{store}/products.json", params={"limit": 250, "page": page}, headers=UA, timeout=30)
        if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
            break
        rows = r.json().get("products", [])
        for p in rows:
            if not p.get("images") or not any(v.get("available", True) for v in p.get("variants", [])):
                continue
            out.append({"handle": p["handle"], "title": p["title"], "created": p.get("created_at") or ""})
        if len(rows) < 250:
            break
        page += 1
    return out


def store_of(c):
    """The company's Shopify domain (cached in its profile once found)."""
    prof = c.get("profile") or {}
    st = (prof.get("shop") or {}).get("store")
    if st:
        return st
    cand = domain(c.get("source_url"))
    if not cand:
        return None
    try:
        if catalog(cand):
            return cand
        # custom domain fronting a myshopify store: the storefront answers /meta.json with its myshopify domain
        m = requests.get(f"https://{cand}/meta.json", headers=UA, timeout=20).json()
        alt = m.get("myshopify_domain")
        return alt if alt and catalog(alt) else None
    except Exception:
        return None


def pick(items, state):
    """Next product: anything new since the last run first, then round-robin through the catalog."""
    seen = set(state.get("done") or [])
    fresh = [p for p in items if p["handle"] not in seen]
    if not fresh:  # whole catalog covered: start a new lap, oldest-posted first
        state["done"] = []
        fresh = items
    fresh.sort(key=lambda p: p["created"], reverse=True)
    return fresh[0]


def eligible(c):
    plan = companies.plan_of(c)
    return bool(plan.get("shop_ads")) or c.get("plan") == "comp"


def work(c, mode, force=False):
    """One day's shift for one store. Returns a short status string."""
    plan = companies.plan_of(c)
    hour = plan.get("shop_hour", 16)
    today = dt.datetime.utcnow().date().isoformat()
    prof = dict(c.get("profile") or {})
    state = dict(prof.get("shop") or {})
    if not force and (dt.datetime.utcnow().hour < hour or state.get("last_day") == today):
        return "not this hour"
    store = store_of(c)
    if not store:
        if c.get("plan") != "comp":
            companies.log(c["id"], "shopteam", "no Shopify store found at your website link. Reply with your store URL "
                                               "(yourstore.com or yourstore.myshopify.com) to start the daily ads.")
        return "no store"
    pfs = [p for p in ("instagram", "tiktok") if accounts.connected(c["id"], p)[0]]
    if not pfs:
        companies.log(c["id"], "shopteam", "today's ad is waiting: connect Instagram on your live page to start posting")
        return "not connected"
    items = catalog(store)
    if not items:
        companies.log(c["id"], "shopteam", f"{store}: no live products with photos to advertise today")
        return "empty catalog"
    p = pick(items, state)
    if not companies.spend(c["id"], companies.plans()["costs"]["video"], f"product ad: {p['title']}"[:120]):
        return "out of credits"
    import shopify_ad
    try:
        res = shopify_ad.make(p["handle"], store=store, account=c["id"], seed=3650 + len(state.get("done") or []),
                              post=False)
        posted = {}
        for pf in pfs:
            import subprocess
            r = subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "--account", c["id"], "--platform", pf,
                                "--video", res["video"], "--caption", res["caption"], "--mode", mode])
            posted[pf] = "posted" if r.returncode == 0 else "failed"
    except Exception as e:
        traceback.print_exc()
        companies.refund(c["id"], companies.plans()["costs"]["video"], f"product ad failed: {p['title']}"[:120])
        companies.log(c["id"], "shopteam", f"ad for {p['title']} failed, credit refunded: {e}"[:300])
        return "failed"
    state.update(store=store, last_day=today, last=p["handle"], done=(state.get("done") or []) + [p["handle"]],
                 count=int(state.get("count") or 0) + 1)
    prof["shop"] = state
    companies.save(c["id"], profile=prof)
    companies.log(c["id"], "shopteam", f"trailer ad for {p['title']} (${res['price']:,.0f}), QR to checkout",
                  {"platforms": posted, "product": p["handle"], "checkout": res["qr"]})
    companies.remember(c["id"], "post", f"{today}: product trailer ad for {p['title']} -> {posted}")
    return f"{p['title']}: {posted}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company")
    ap.add_argument("--now", action="store_true", help="ignore the posting hour / once-a-day guard")
    ap.add_argument("--check", metavar="URL", help="check a store link and exit")
    ap.add_argument("--mode", default=os.environ.get("IRUN_MODE", "draft"), choices=["draft", "live"])
    a = ap.parse_args()
    if a.check:
        d = domain(a.check)
        items = catalog(d)
        print(json.dumps({"store": d, "shopify": bool(items), "products": len(items),
                          "first": [i["title"] for i in items[:5]]}, indent=2))
        return
    if not db.enabled():
        sys.exit("Shop Team needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
    print(f"=== iRun Shop Team === mode={a.mode}")
    for c in companies.all_companies("active"):
        if (a.company and c["id"] != a.company) or not eligible(c):
            continue
        try:
            print(f"[{c['id']}] {work(c, a.mode, a.now)}")
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
