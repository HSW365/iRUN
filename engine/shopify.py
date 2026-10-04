"""Read a Shopify store's public catalog (the /products.json feed every Shopify storefront serves).

Used by store_scan.py (onboard a brand from its store URL) and competitors.py (price benchmarks).
Only public storefront data is read: no login, no admin API, no customer data.
"""
import html
import ipaddress
import re
import statistics
from collections import Counter
from urllib.parse import urlparse

import requests

UA = {"User-Agent": "iRun/1.0 (+https://hsw365.github.io/iRUN/)", "Accept": "application/json,text/html"}


def normalize(url):
    """'hsw365.co/collections/all' -> 'https://hsw365.co'. Raises ValueError on anything that isn't a public host."""
    url = (url or "").strip()
    if not url:
        raise ValueError("store URL is empty")
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if not host or "." not in host or host.endswith((".local", ".internal")) or host == "localhost":
        raise ValueError(f"not a public store address: {url!r}")
    try:
        ipaddress.ip_address(host)
        raise ValueError("store URL must be a domain name, not an IP address")
    except ValueError as e:
        if "domain name" in str(e):
            raise
    return f"https://{host}"


def host_of(base):
    h = urlparse(base).hostname or ""
    return h[4:] if h.startswith("www.") else h


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def account_id(base):
    h = host_of(base)
    h = h[: -len(".myshopify.com")] if h.endswith(".myshopify.com") else h
    return re.sub(r"[^a-z0-9]", "", h)


def strip_html(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def fetch_products(base, max_pages=4):
    """Up to max_pages x 250 products. Raises RuntimeError when the store doesn't expose the feed."""
    out = []
    for page in range(1, max_pages + 1):
        r = requests.get(f"{base}/products.json", params={"limit": 250, "page": page}, headers=UA, timeout=30)
        if r.status_code != 200:
            if page == 1:
                raise RuntimeError(f"{base}/products.json returned {r.status_code}. "
                                   "The store is not on Shopify, is password-protected, or blocks the feed.")
            break
        try:
            batch = r.json().get("products", [])
        except ValueError:
            if page == 1:
                raise RuntimeError(f"{base} did not return a Shopify product feed (not JSON).")
            break
        out.extend(batch)
        if len(batch) < 250:
            break
    return out


def fetch_meta(base):
    """Store name and description from the home page. Never raises: a store that blocks it just gets blanks."""
    meta = {"title": "", "site_name": "", "description": ""}
    try:
        r = requests.get(base, headers=UA, timeout=30)
        if r.status_code != 200:
            return meta
        page = r.text[:400000]
    except requests.RequestException:
        return meta

    def tag(pattern):
        m = re.search(pattern, page, re.I | re.S)
        return strip_html(m.group(1)) if m else ""

    meta["title"] = tag(r"<title[^>]*>(.*?)</title>")
    meta["site_name"] = tag(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']')
    meta["description"] = (tag(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']')
                           or tag(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']'))
    return meta


def prices(product):
    out = []
    for v in product.get("variants") or []:
        try:
            out.append(float(v.get("price")))
        except (TypeError, ValueError):
            pass
    return out


def price(product):
    """Lowest variant price, or None."""
    p = prices(product)
    return min(p) if p else None


def tags(product):
    t = product.get("tags") or []
    if isinstance(t, str):
        t = t.split(",")
    return [x.strip().lower() for x in t if x.strip()]


def on_sale(product):
    for v in product.get("variants") or []:
        try:
            if v.get("compare_at_price") and float(v["compare_at_price"]) > float(v["price"]):
                return True
        except (TypeError, ValueError):
            pass
    return False


def in_stock(product):
    return any(v.get("available", True) for v in product.get("variants") or [])


def _stats(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return {"min": round(values[0], 2), "median": round(statistics.median(values), 2), "max": round(values[-1], 2)}


def summarize(products):
    """Catalog facts: counts, product types, price range, tags. Everything here is read off the feed, not guessed."""
    n = len(products)
    types = Counter((p.get("product_type") or "").strip() for p in products)
    types.pop("", None)
    by_type = {}
    for t, count in types.most_common(12):
        by_type[t] = {"count": count, "price": _stats(price(p) for p in products if (p.get("product_type") or "").strip() == t)}
    tag_counts = Counter(t for p in products for t in tags(p))
    described = sum(1 for p in products if len(strip_html(p.get("body_html"))) >= 40)
    return {
        "products": n,
        "types": by_type,
        "vendors": [v for v, _ in Counter((p.get("vendor") or "").strip() for p in products).most_common(5) if v],
        "price": _stats(price(p) for p in products),
        "top_tags": [t for t, _ in tag_counts.most_common(15)],
        "on_sale_pct": round(100 * sum(on_sale(p) for p in products) / n) if n else 0,
        "in_stock_pct": round(100 * sum(in_stock(p) for p in products) / n) if n else 0,
        "with_description_pct": round(100 * described / n) if n else 0,
    }
