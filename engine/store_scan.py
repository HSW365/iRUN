"""Store scan: paste a Shopify store URL, get a brand profile iRun can post for.

Reads the store's public catalog and home page, then builds:
  - catalog facts (what it sells, price range, product types, tags)
  - brand voice and audience (written by Claude from those facts when ANTHROPIC_API_KEY is set;
    otherwise a plain summary taken from the store's own words)
  - an account entry for config/accounts.json: content subjects with a pitch, keyword, link and angles
The analysis is saved to content/intel/<account>-store.json. New accounts are added disabled, so nothing is
made or posted for them until you read the profile and set "enabled": true.
"""
import datetime as dt
import json
import os
import re
from collections import Counter

import shopify
import writer

ROOT = os.path.join(os.path.dirname(__file__), "..")
INTEL = os.path.join(ROOT, "content", "intel")
ACCOUNTS = os.path.join(ROOT, "config", "accounts.json")
MAX_SUBJECTS = 6
STOP = {"the", "and", "for", "with", "your", "our", "new", "shop", "store", "from", "this", "that", "all"}

AI_SYSTEM = """You profile an online store for a short-form video team. You are given facts read from the store's
public catalog. Use only those facts. Do not invent products, prices, discounts, guarantees, reviews, awards,
statistics or claims about results. No emojis.
Return ONLY JSON:
{"voice": "2-3 sentences: who the brand is and how it talks, written as a brief for a script writer",
 "audience": "1 sentence: who buys from this store",
 "subjects": [{"id": "<id given>", "audience": "who this is for", "angles": ["3 short video angles, 3-8 words each"]}]}"""


def brand_name(meta, products, base):
    if meta.get("site_name"):
        return meta["site_name"]
    title = re.split(r"\s+[|–—-]\s+", meta.get("title") or "")[0].strip()
    if title and len(title) <= 40:
        return title
    vendors = Counter((p.get("vendor") or "").strip() for p in products)
    vendors.pop("", None)
    if vendors:
        return vendors.most_common(1)[0][0]
    return shopify.host_of(base)


def _keyword(name, used):
    for w in re.findall(r"[A-Za-z0-9]+", name):
        if len(w) >= 3 and w.lower() not in STOP and w.upper() not in used:
            used.add(w.upper())
            return w.upper()
    k = "SHOP"
    n = 2
    while k in used:
        k, n = f"SHOP{n}", n + 1
    used.add(k)
    return k


def _sentences(text, limit=280):
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if len(out) + len(s) > limit:
            break
        out = (out + " " + s).strip()
    return out or text[:limit].rsplit(" ", 1)[0]


def _cta(host):
    return {"spoken": f"Shop it at {host.replace('.', ' dot ')}",
            "screen": [f"SHOP {host.upper()}", "LINK IN BIO"],
            "caption": f"Shop it at {host}. Link in bio."}


def subjects(base, brand, products):
    """What iRun will make content about: product types when the store has several, otherwise single products."""
    host = shopify.host_of(base)
    types = Counter((p.get("product_type") or "").strip() for p in products)
    types.pop("", None)
    used, out = set(), []
    if len(types) >= 2:
        for t, _ in types.most_common(MAX_SUBJECTS):
            group = [p for p in products if (p.get("product_type") or "").strip() == t]
            titles = [p["title"] for p in group[:5]]
            out.append({
                "id": shopify.slug(t)[:40], "name": t.upper()[:40], "keyword": _keyword(t, used), "link": base,
                "cta": _cta(host), "audience": f"shoppers looking for {t.lower()}",
                "pitch": f"{brand} {t.lower()}: " + ", ".join(titles) + ("." if len(group) <= 5 else ", and more."),
                "angles": [f"what makes {brand} {t.lower()} different", f"who {t.lower()} is for", f"the story behind {brand}"],
            })
    else:
        for p in products[:MAX_SUBJECTS]:
            desc = shopify.strip_html(p.get("body_html"))
            out.append({
                "id": (p.get("handle") or shopify.slug(p["title"]))[:40], "name": p["title"].upper()[:40],
                "keyword": _keyword(p["title"], used), "link": f"{base}/products/{p.get('handle', '')}",
                "cta": _cta(host), "audience": f"people shopping at {brand}",
                "pitch": _sentences(desc) if len(desc) >= 40 else f"{p['title']} from {brand}.",
                "angles": [f"what makes {p['title']} different", f"who {p['title']} is for", f"the story behind {brand}"],
            })
    seen = set()
    for s in out:  # ids must be unique within the account
        base_id, n = s["id"] or "item", 2
        while s["id"] in seen or not s["id"]:
            s["id"], n = f"{base_id}-{n}", n + 1
        seen.add(s["id"])
    return out


def plain_voice(brand, meta, catalog):
    kinds = ", ".join(list(catalog["types"])[:4]).lower()
    desc = meta.get("description") or ""
    return (f"{brand}" + (f", which sells {kinds}" if kinds else "") + ". "
            + (f"In the store's own words: \"{_sentences(desc, 220)}\" " if desc else "")
            + "Plain, confident and specific. Say only what the store itself says about its products.")


def plain_audience(catalog):
    kinds = ", ".join(list(catalog["types"])[:3]).lower()
    tags = ", ".join(catalog["top_tags"][:5])
    return ("Shoppers looking for " + (kinds or "what this store sells")
            + (f". Catalog tags point to interest in: {tags}." if tags else "."))


def ai_profile(brand, meta, catalog, subs, products):
    facts = {
        "brand": brand, "store_description": meta.get("description"), "catalog": catalog,
        "subjects": [{"id": s["id"], "name": s["name"], "pitch": s["pitch"]} for s in subs],
        "sample_products": [{"title": p["title"], "type": p.get("product_type"),
                             "description": shopify.strip_html(p.get("body_html"))[:400]} for p in products[:12]],
    }
    return writer.ask_json(AI_SYSTEM, json.dumps(facts), max_tokens=1500)


def scan(url, handle=None, use_ai=None):
    """Returns {"account": <entry for accounts.json>, "analysis": <saved to content/intel>}."""
    base = shopify.normalize(url)
    products = shopify.fetch_products(base)
    if not products:
        raise RuntimeError(f"{base} has no published products in its feed.")
    meta = shopify.fetch_meta(base)
    brand = brand_name(meta, products, base)
    catalog = shopify.summarize(products)
    subs = subjects(base, brand, products)
    voice, audience, source = plain_voice(brand, meta, catalog), plain_audience(catalog), "catalog"

    if use_ai is None:
        use_ai = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if use_ai:
        try:
            ai = ai_profile(brand, meta, catalog, subs, products)
            voice, audience, source = ai.get("voice") or voice, ai.get("audience") or audience, "claude"
            by_id = {s.get("id"): s for s in ai.get("subjects") or []}
            for s in subs:
                extra = by_id.get(s["id"]) or {}
                if extra.get("audience"):
                    s["audience"] = str(extra["audience"])
                angles = [str(a) for a in extra.get("angles") or [] if str(a).strip()][:3]
                if angles:
                    s["angles"] = angles
        except Exception as e:  # the catalog profile still stands
            print(f"[scan] Claude profile failed ({e}); using the catalog summary")

    aid = shopify.account_id(base)
    account = {"id": aid, "brand": brand, "handle": (handle or aid).lstrip("@"), "type": "client", "enabled": False,
               "platforms": ["tiktok", "instagram"], "lead_bot": False, "store": base, "voice": voice,
               "products": subs}
    analysis = {"account": aid, "store": base, "scanned_at": dt.datetime.utcnow().isoformat() + "Z",
                "brand": brand, "profile_source": source, "voice": voice, "audience": audience, "catalog": catalog,
                "subjects": [{"id": s["id"], "name": s["name"], "keyword": s["keyword"], "audience": s["audience"],
                              "angles": s["angles"]} for s in subs]}
    return {"account": account, "analysis": analysis}


def save(result, accounts_path=ACCOUNTS, intel_dir=INTEL):
    """Writes the analysis and adds the account if it is new. An existing account is never overwritten:
    it only gains its store URL. Returns 'added' or 'exists'."""
    os.makedirs(intel_dir, exist_ok=True)
    aid = result["account"]["id"]
    with open(os.path.join(intel_dir, f"{aid}-store.json"), "w") as f:
        json.dump(result["analysis"], f, indent=2)
    with open(accounts_path) as f:
        cfg = json.load(f)
    existing = next((a for a in cfg["accounts"] if a["id"] == aid), None)
    if existing:
        state = "exists"
        if existing.get("store") == result["account"]["store"]:
            return state
        existing["store"] = result["account"]["store"]
    else:
        state = "added"
        cfg["accounts"].append(result["account"])
    with open(accounts_path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    return state
