"""Onboarding agent: a website and/or social handles in, a full company profile out.

Reads the business's website, then Claude writes the profile the other agents run on: brand voice, the
products or services to promote (with calls to action), a faceless video series, and the outreach pitch.
Only facts found on the site or given by the owner go in. Nothing is invented.
"""
import html
import re
import urllib.parse

import requests

import companies
import llm

UA = {"User-Agent": "Mozilla/5.0 (compatible; iRunOperator/1.0; +https://hsw365.github.io/iRUN/)"}

SYSTEM = """You are the onboarding agent of iRun Operator, an AI that runs marketing for a small business.
From the website text and the owner's notes, build the business profile the other agents will use.

Hard rules:
- Use only facts present in the material. Never invent services, prices, awards, years in business, reviews,
  statistics, locations, phone numbers or guarantees. If a detail is missing, leave it out.
- No prices unless the material states them.
- Keywords are one short uppercase word.
- Every call to action must be something the business actually supports (call a number shown, visit the site,
  link in bio, DM). Prefer "Link in bio" when unsure.
- Health, legal, financial or safety businesses: no advice claims; send people to the business.
- No emojis.

Return ONLY JSON:
{
 "brand": "business name as written",
 "handle": "main social handle without @ if given, else empty",
 "summary": "2 sentences on what the business is and who it serves",
 "voice": "one paragraph describing the business and how its videos should sound, including facts the writer must respect",
 "location": "city/region if stated, else empty",
 "contact": {"phone": "", "email": "", "website": ""},
 "facts": ["8-20 short verified facts from the material"],
 "products": [ 1 to 5 of
   {"id": "lowercase-slug", "name": "UPPERCASE SHORT NAME", "keyword": "WORD", "link": "url or empty",
    "cta": {"spoken": "spoken call to action", "screen": ["LINE ONE", "LINE TWO"], "caption": "caption CTA line"},
    "audience": "who buys this", "pitch": "what it is, only stated facts", "angles": ["3-5 video angles"]} ],
 "series": {"id": "main", "name": "UPPERCASE SERIES NAME", "style": "one of cinematic, noir, anime, comic, 3d, dark-fantasy, cyberpunk, oil, watercolor, vintage, photoreal, minimal",
   "topic": "what the faceless story videos are about (useful tips or stories for this business's customers)",
   "audience": "who watches", "angles": ["6 video ideas"],
   "cta": {"spoken": "short follow or call line", "screen": ["LINE ONE", "LINE TWO"], "caption": "caption line"}},
 "outreach": {"ideal_customer": "who the cold emails go to (businesses, never consumers)",
   "offer": "what the email offers, only real services", "sender": "the business name to sign as"},
 "site_brief": {"headline": "short headline", "sections": ["4-7 section ideas grounded in the facts"],
   "primary_cta": "the main action", "palette_hint": "colors seen on the site or fitting the brand"}
}"""


def page_text(url, limit=18000):
    """Visible text, title, description and contact links of one page."""
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    raw = r.text
    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', raw, re.I)
    links = set(re.findall(r'href=["\'](tel:[^"\']+|mailto:[^"\']+|https?://(?:www\.)?(?:instagram|tiktok|facebook|youtube|x|twitter|linkedin)\.com/[^"\']+)', raw, re.I))
    body = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    body = re.sub(r"\s+", " ", body).strip()
    internal = []
    host = urllib.parse.urlparse(r.url).netloc
    for h in re.findall(r'href=["\']([^"\'#]+)', raw, re.I):
        u = urllib.parse.urljoin(r.url, h)
        if urllib.parse.urlparse(u).netloc == host and u not in internal and not re.search(r"\.(jpg|png|pdf|css|js|svg|webp)$", u, re.I):
            internal.append(u)
    out = (f"URL: {r.url}\nTITLE: {title.group(1).strip() if title else ''}\n"
           f"DESCRIPTION: {desc.group(1).strip() if desc else ''}\nCONTACT/SOCIAL LINKS: {sorted(links)}\n"
           f"TEXT: {body[:limit]}")
    return out, internal


def gather(url):
    """Home page plus up to 4 key inner pages (about, services, contact, menu, shop)."""
    if not url:
        return ""
    if not re.match(r"https?://", url):
        url = "https://" + url
    home, internal = page_text(url)
    parts = [home]
    keys = ("about", "service", "contact", "menu", "shop", "product", "pricing", "work")
    picked = [u for u in internal if any(k in u.lower() for k in keys)][:4]
    for u in picked:
        try:
            parts.append(page_text(u, 6000)[0])
        except Exception as e:
            parts.append(f"URL: {u}\n(could not read: {e})")
    return "\n\n=====\n\n".join(parts)


def onboard(c):
    """Build and save the profile for one irun_companies row. Returns the profile."""
    cid = c["id"]
    companies.log(cid, "onboard", f"reading {c.get('source_url') or 'owner notes'}")
    material = ""
    if c.get("source_url"):
        try:
            material = gather(c["source_url"])
        except Exception as e:
            companies.log(cid, "onboard", f"could not read the website: {e}")
    if not material and not c.get("notes"):
        raise ValueError("nothing to read: no reachable website and no notes")
    handles = c.get("handles") or {}
    user = (f"Business name given: {c['name']}\nSocial handles given: {handles}\n"
            f"Owner notes: {c.get('notes') or '(none)'}\n\nWEBSITE MATERIAL:\n{material or '(no website)'}")
    prof = llm.ask_json(SYSTEM, user, max_tokens=6000)
    prof["products"] = [clean_product(p) for p in prof.get("products", []) if p.get("name") and p.get("pitch")][:5]
    if not prof["products"]:
        raise ValueError("the profile came back with no products or services")
    if not prof.get("handle"):
        prof["handle"] = (handles.get("instagram") or handles.get("tiktok") or "").lstrip("@")
    companies.save(cid, profile=prof, status="active", error=None)
    for f in prof.get("facts", []):
        companies.remember(cid, "fact", f)
    companies.remember(cid, "decision", f"Onboarded. Promoting: {', '.join(p['name'] for p in prof['products'])}.")
    companies.log(cid, "onboard", f"profile ready: {len(prof['products'])} offers, {len(prof.get('facts', []))} facts",
                  {"products": [p["name"] for p in prof["products"]]})
    return prof


def clean_product(p):
    p["id"] = companies.slug(p.get("id") or p["name"])[:24]
    p["keyword"] = re.sub(r"[^A-Z0-9]", "", str(p.get("keyword") or p["name"]).upper())[:12] or "INFO"
    cta = p.get("cta") or {}
    screen = (list(cta.get("screen") or []) + ["LINK IN BIO", p["name"]])[:2]
    p["cta"] = {"spoken": cta.get("spoken") or "Link in bio", "screen": [s.upper()[:28] for s in screen],
                "caption": cta.get("caption") or "Link in bio."}
    p["angles"] = [a for a in p.get("angles", []) if a][:5] or [p["pitch"]]
    p.setdefault("audience", "")
    p.setdefault("link", "")
    return p
