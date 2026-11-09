"""Generate a reviewable batch of product ads from a Shopify catalog.

Examples:
  python engine/shopify_ad_burst.py --store hsw365.co --limit 12
  python engine/shopify_ad_burst.py --store hsw365.co --limit 12 --render

Draft generation is fast and does not publish. Rendering is opt-in because it is
CPU/AI intensive. Publishing is deliberately not automated by this command.
"""
import argparse
import datetime as dt
import json
import os
import re
import socket
import sys
import uuid
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import shopify_ad
import shopteam

UA = {"User-Agent": "Mozilla/5.0 (compatible; iRunAdBurst/1.0; +https://hsw365.co)"}


def normalize_store(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError("A Shopify store domain is required.")
    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a public HTTPS Shopify storefront domain.")
    if parsed.port not in (None, 443):
        raise ValueError("Custom ports are not supported.")
    host = parsed.hostname.lower().rstrip(".")
    if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
        raise ValueError("That store domain is not valid.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private and local network hosts are not allowed.")
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("The store domain could not be resolved.") from exc
    import ipaddress
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Only public internet storefronts are supported.")
    return host


def tracked(url, campaign_id, medium):
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"utm_source": "irun", "utm_medium": medium, "utm_campaign": campaign_id})
    return urlunparse(parts._replace(query=urlencode(query)))


def main():
    ap = argparse.ArgumentParser(description="Create up to 12 Shopify product ad drafts.")
    ap.add_argument("--store", default="hsw365.co", help="Shopify storefront domain or HTTPS URL")
    ap.add_argument("--limit", type=int, default=12, choices=range(1, 13))
    ap.add_argument("--account", default="hoodstar365")
    ap.add_argument("--render", action="store_true", help="Render full MP4 videos; otherwise create ad specs/captions only")
    ap.add_argument("--output", default=os.path.join(ROOT, "out", "ad-burst"))
    a = ap.parse_args()

    store = normalize_store(a.store)
    products = shopteam.catalog(store)
    if not products:
        raise SystemExit("No purchasable Shopify products with images were found.")
    selected = products[:a.limit]
    campaign_id = "irun-" + uuid.uuid4().hex[:12]
    os.makedirs(a.output, exist_ok=True)
    manifest = {
        "campaign_id": campaign_id,
        "store": store,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "drafts",
        "rendered": bool(a.render),
        "requested": a.limit,
        "available_products": len(products),
        "ads": [],
        "measurement": "UTM-tagged product and checkout links; clicks and orders are reported by Shopify/connected platform analytics when available."
    }

    for index, product in enumerate(selected, 1):
        row = {"position": index, "handle": product["handle"], "title": product["title"], "status": "pending"}
        try:
            result = shopify_ad.make(
                product["handle"], store=store, account=a.account,
                seed=3650 + index * 97, post=False, spec_only=not a.render, campaign_id=campaign_id
            )
            with open(result["spec"], "r", encoding="utf-8") as f:
                spec = json.load(f)
            spec["campaign_id"] = campaign_id
            spec["tracking"] = {"source": "irun", "medium": "social", "campaign": campaign_id}
            spec["end"]["link"] = tracked(spec["end"]["link"], campaign_id, "social")
            result["caption"] = result["caption"].replace(
                f"https://{store}/products/{product['handle']}",
                tracked(f"https://{store}/products/{product['handle']}", campaign_id, "social")
            )
            spec["caption"] = result["caption"]
            with open(result["spec"], "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2)
            row.update({
                "status": "rendered" if a.render else "draft",
                "price": result["price"],
                "playbook": result["playbook"],
                "spec": os.path.relpath(result["spec"], ROOT),
                "caption": result["caption"],
                "product_url": tracked(f"https://{store}/products/{product['handle']}", campaign_id, "social"),
                "checkout_url": spec["end"]["link"],
            })
            if a.render:
                row["video"] = os.path.relpath(result["video"], ROOT)
        except Exception as exc:
            row.update(status="failed", error=str(exc)[:500])
        manifest["ads"].append(row)
        print(json.dumps({"completed": index, "total": len(selected), "title": product["title"], "status": row["status"]}), flush=True)

    manifest["completed"] = sum(x["status"] in ("draft", "rendered") for x in manifest["ads"])
    manifest["failed"] = sum(x["status"] == "failed" for x in manifest["ads"])
    manifest["status"] = "complete" if manifest["failed"] == 0 else "partial"
    path = os.path.join(a.output, f"{campaign_id}-manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps({"manifest": path, "campaign_id": campaign_id, "completed": manifest["completed"],
                      "failed": manifest["failed"], "rendered": a.render}, indent=2))
    if manifest["completed"] == 0:
        raise SystemExit("No ads were generated successfully.")


if __name__ == "__main__":
    main()
