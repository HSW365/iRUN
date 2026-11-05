"""Shop Team leads: finds live U.S. Shopify stores, reads the contact email they publish, and queues a personal first
email for the HSW365 Sales Autopilot (engine/sales.py), which sends it, answers replies and follows up.

Free route, no paid data:
  discover  Common Crawl's public URL index lists *.myshopify.com storefronts it has crawled (a fresh slice each run)
  qualify   /meta.json + /products.json: live (no password page), U.S. or USD, at least 3 products with photos
  contact   the email the store publishes on its contact-information policy, contact page or homepage footer
  draft     a short personal email naming three of the store's own products as its first three daily ads,
            linking to shopteam.html?store=<domain> where those ads preview instantly

Leads go in as status 'approved' with product 'shopteam', so sales.py sends them first (within SALES_DAILY_CAP),
skips anyone on the suppression list, and answers replies with the Shop Team facts from config/products.json.

  python engine/shopify_leads.py --need 40        top the queue up to 40 waiting Shop Team leads
  python engine/shopify_leads.py --try store.com  qualify one store and print the draft (no insert)
"""
import argparse
import datetime as dt
import html
import json
import os
import random
import re
import sys
import time
import urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; HSW365-ShopTeam/1.0; +https://hsw365.github.io/iRUN/shopteam.html)"}
PAGE = "https://hsw365.github.io/iRUN/shopteam.html"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
SKIP_LOCAL = re.compile(r"^(no-?reply|donotreply|postmaster|abuse|webmaster|privacy|legal|dmca|example|test|user|name|"
                        r"email|your|sentry|support@shopify)", re.I)
SKIP_DOMAIN = re.compile(r"(shopify\.com|myshopify\.com|example\.|sentry|wixpress|domain\.com|email\.com|godaddy|"
                         r"\.(png|jpe?g|gif|webp|svg|css|js)$)", re.I)
HOUSE = {"hsw365.co", "www.hsw365.co"}
try:
    with open(os.path.join(HERE, "..", "config", "owners.json")) as _f:
        OWNERS = {e.lower() for e in json.load(_f)["emails"]} | {"hswmerch@gmail.com"}
except Exception:
    OWNERS = {"hswmerch@gmail.com"}
CONTACT_PATHS = ["/policies/contact-information", "/pages/contact", "/pages/contact-us", "/"]


def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=kw.pop("timeout", 20), **kw)
    except Exception:
        return None


# ---------------------------------------------------------------- discover
def crawl_indexes():
    for _ in range(3):
        r = get("https://index.commoncrawl.org/collinfo.json", timeout=40)
        if r is not None and r.ok:
            try:
                return [c["cdx-api"] for c in r.json()]
            except Exception:
                pass
        print(f"crawl index list: {getattr(r, 'status_code', 'no response')}")
        time.sleep(10)
    return []


def discover(want, seen):
    """Up to `want` *.myshopify.com hosts not seen before, from a random page of a recent Common Crawl index."""
    out = []
    for api in crawl_indexes()[:3]:
        base = f"{api}?url=*.myshopify.com&output=json&fl=url&filter=status:200"
        pages = 0
        for _ in range(3):
            r = get(base + "&showNumPages=true", timeout=90)
            try:
                pages = int(r.json()["pages"]) if r is not None and r.ok else 0
            except Exception:
                pages = 0
            if pages:
                break
            print(f"{api}: page count {getattr(r, 'status_code', 'no response')} {(getattr(r, 'text', '') or '')[:120]}")
            time.sleep(15)
        for _ in range(4):
            if not pages or len(out) >= want:
                break
            r = get(f"{base}&page={random.randrange(pages)}", timeout=120)
            if r is None or not r.ok:
                print(f"{api}: page fetch {getattr(r, 'status_code', 'no response')}")
                time.sleep(10)
                continue
            for line in r.text.splitlines():
                try:
                    host = urllib.parse.urlparse(json.loads(line)["url"]).hostname or ""
                except Exception:
                    continue
                if host.endswith(".myshopify.com") and host not in seen and host.count(".") == 2:
                    seen.add(host)
                    out.append(host)
            time.sleep(2)
        if len(out) >= want:
            break
    random.shuffle(out)
    return out[:want]


# ---------------------------------------------------------------- qualify + contact
def qualify(host):
    """Store facts when this is a live U.S./USD Shopify store with 3+ products with photos, else None."""
    m = get(f"https://{host}/meta.json")
    if m is None or not m.ok or "json" not in m.headers.get("content-type", ""):
        return None
    try:
        meta = m.json()
    except Exception:
        return None
    if meta.get("country") not in ("US", None) and meta.get("currency") != "USD":
        return None
    domain = (meta.get("domain") or host).lower()
    p = get(f"https://{domain}/products.json", params={"limit": 30})
    if p is None or not p.ok or "/password" in p.url:
        return None
    try:
        prods = [x for x in p.json().get("products", []) if x.get("images")]
    except Exception:
        return None
    if len(prods) < 3:
        return None
    picks = []
    for x in prods:
        t = re.sub(r"\s+", " ", html.unescape(x["title"])).strip()
        if 3 <= len(t) <= 70 and t.lower() not in {q.lower() for q in picks}:
            picks.append(t)
        if len(picks) == 3:
            break
    if len(picks) < 3:
        return None
    name = (meta.get("name") or "").strip()
    if not name or "." in name and " " not in name:  # "mystore.com" -> "Mystore"
        name = re.sub(r"^www\.", "", domain).split(".")[0].replace("-", " ").title()
    return {"host": host, "domain": domain, "name": name[:80],
            "city": meta.get("city"), "state": meta.get("province_code") or meta.get("province"),
            "count": meta.get("published_products_count") or len(prods), "products": picks,
            "type": (prods[0].get("product_type") or "").strip()[:40]}


def contact_email(domain):
    root = domain.split(".")[-2] if domain.count(".") >= 1 else domain
    best = None
    for path in CONTACT_PATHS:
        r = get(f"https://{domain}{path}")
        if r is None or not r.ok:
            continue
        text = html.unescape(r.text).replace("[at]", "@").replace("(at)", "@")
        for raw in EMAIL.findall(text):
            e = raw.strip(".").lower()
            local, _, dom = e.partition("@")
            if SKIP_LOCAL.match(local) or SKIP_DOMAIN.search(dom) or len(e) > 80:
                continue
            if root in dom:  # the store's own domain beats a gmail address
                return e
            best = best or e
        if best:
            return best
    return best


# ---------------------------------------------------------------- draft
def draft(s):
    a, b, c = (html.escape(x) for x in s["products"])
    name = html.escape(s["name"])
    link = f"{PAGE}?store={urllib.parse.quote(s['domain'])}&src=email#preview"
    subject = f"{s['name']}: your next 3 ads are already picked"[:110]
    body = (f"<p>Hi {name} team,</p>"
            f"<p>I'm Elvin Torres Sr., founder of HSW365 Media. I went through {html.escape(s['domain'])} and picked "
            f"the first three products my AI marketing team would advertise for you:</p>"
            f"<p>Day 1: <b>{a}</b><br>Day 2: <b>{b}</b><br>Day 3: <b>{c}</b></p>"
            "<p><b>iRun Shop Team</b> makes a new cinematic video ad for one of your products every day, built from your "
            "own product photos and pages, and posts it to your Instagram. Every ad ends on a QR that opens checkout with "
            "that product already in the cart.</p>"
            "<p>It's free. No card, no app to install, no login to share, no cut of your sales, stop any time.</p>"
            f'<p>See your first week of ads here (it loads your real products): <a href="{link}">{PAGE.split("//")[1]}</a></p>'
            "<p>Or just reply <b>\"YES\"</b> and I'll set your store up myself.</p>")
    follow = (f"<p>Hi {name} team,</p>"
              f"<p>Quick follow-up. Your Day 1 ad for <b>{a}</b> is still waiting. The team makes one every day for "
              "free and posts it for you, with a QR straight to checkout.</p>"
              f'<p>Preview your week: <a href="{link}">see your ads</a>. Reply "YES" and I\'ll set it up. '
              "If it's not a fit, no problem.</p>")
    return subject, body, follow


# ---------------------------------------------------------------- run
def waiting():
    return len(db.select("irun_sales_leads", "product=eq.shopteam&status=in.(approved,new)&select=email&limit=1000"))


def known(email):
    return bool(db.select("irun_sales_leads", f"email=eq.{urllib.parse.quote(email)}&select=email")) or bool(
        db.select("irun_suppress", f"email=eq.{urllib.parse.quote(email)}&select=email"))


def stock(need, budget_min=25):
    import sales
    have = waiting()
    if have >= need:
        print(f"shop team leads waiting: {have}")
        return 0
    seen = set(json.loads(sales.setting("shopteam_seen_hosts", "[]") or "[]")[-20000:])
    stop = time.time() + budget_min * 60
    added, checked = 0, 0
    while have + added < need and time.time() < stop:
        hosts = discover(150, seen)
        if not hosts:
            print("no new stores from the crawl index this run")
            break
        for host in hosts:
            if have + added >= need or time.time() > stop:
                break
            checked += 1
            s = qualify(host)
            if not s:
                continue
            if s["domain"] in HOUSE:
                continue
            e = contact_email(s["domain"])
            if not e or e in OWNERS or known(e):
                continue
            subject, body, follow = draft(s)
            row = {"email": e, "business": s["name"], "trade": (s["type"] or "online store").lower()[:60],
                   "city": s["city"], "state": (s["state"] or "")[:10] or None, "source": "shopify-crawl",
                   "product": "shopteam", "campaign": "shopteam-launch", "website": f"https://{s['domain']}",
                   "subject": subject, "body": body, "followup_body": follow, "status": "approved",
                   "approved_at": dt.datetime.utcnow().isoformat() + "Z",
                   "note": f"{s['count']} products. First ads: {'; '.join(s['products'])}"}
            n = sales.add_leads([row])
            added += n
            if n:
                print(f"+ {s['name']} <{e}> {s['domain']}")
    sales.set_setting("shopteam_seen_hosts", json.dumps(sorted(seen)[-20000:]))
    sales.log("leads", None, f"shop team: {checked} stores checked, {added} new leads")
    print(f"shop team: {checked} stores checked, {added} new leads, {have + added} waiting")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--need", type=int, default=int(os.environ.get("SHOPTEAM_LEADS") or 30))
    ap.add_argument("--minutes", type=int, default=25)
    ap.add_argument("--try", dest="one", metavar="STORE")
    a = ap.parse_args()
    if a.one:
        s = qualify(re.sub(r"^https?://", "", a.one).split("/")[0])
        if not s:
            sys.exit("not a live U.S. Shopify store with 3+ products")
        s["email"] = contact_email(s["domain"])
        subject, body, _ = draft(s)
        print(json.dumps(s, indent=2)); print(subject); print(body)
        return
    if not db.enabled():
        sys.exit("needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
    stock(a.need, a.minutes)


if __name__ == "__main__":
    main()
