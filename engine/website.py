"""Website agent: builds a one-page site for a company from its profile.

Draft -> Supabase storage (sites/<id>/draft.html), previewed in the dashboard. Once the owner approves it,
the next Operator run publishes it to this repo at sites/<id>/index.html, served by GitHub Pages at
https://hsw365.github.io/iRUN/sites/<id>/. Rebuilds go back to draft and wait for approval again.
"""
import json
import os
import re
import tempfile

import companies
import db
import llm

ROOT = os.path.join(os.path.dirname(__file__), "..")
PAGES = "https://hsw365.github.io/iRUN/sites"

SYSTEM = """You are a senior web designer and front-end developer at a top agency. You build one-page websites for
small businesses that look like a custom $30,000 build: confident typography, strong hierarchy, generous spacing,
a deliberate color system, real content. Never generic, never template-looking.

Output a single complete HTML document and nothing else (no markdown fences, no commentary).

Technical rules:
- One file. All CSS in one <style> tag. No JavaScript at all, no <script> tags. No external images.
- Fonts: at most two families from Google Fonts via <link>. Everything else system.
- Visuals come from CSS only: color fields, gradients, shapes, large type, borders, SVG inline icons drawn by you.
- Mobile first, works from 360px wide up; no horizontal scroll. Semantic HTML, alt-free (no <img>), good contrast.
- Include <title>, meta description, viewport, Open Graph title/description, and <meta name="robots" content="index,follow">.
- Phone numbers as tel: links, emails as mailto: links, the main website/booking link as given.

Content rules:
- Use ONLY the facts provided. Never invent reviews, testimonials, ratings, prices, years in business, awards,
  team members, addresses, certifications, statistics or guarantees. If a fact is missing, design around it.
- Sections: hero with headline and primary call to action, what they offer, why them (only real facts),
  how it works or what to expect, area served if stated, a closing call to action, and a footer with contact.
- Copy is short, specific and human. No emojis. No lorem ipsum. No placeholder text of any kind.
- Footer ends with a small line: "Site by iRun".
"""


def build(c, notes=None):
    """Write a new draft for this company. Returns the draft URL."""
    cid, prof = c["id"], c.get("profile") or {}
    if not companies.spend(cid, companies.plans()["costs"]["site"], "website build"):
        return None
    companies.log(cid, "site", "designing the website")
    try:
        lessons = [m["content"] for m in companies.memories(cid, 30) if m["kind"] in ("lesson", "decision")][:10]
        brief = {k: prof.get(k) for k in ("brand", "summary", "location", "contact", "facts", "products", "site_brief")}
        user = ("Build the website for this business.\n\nPROFILE:\n" + json.dumps(brief, indent=1)
                + (f"\n\nNOTES FROM THE OPERATOR'S REVIEWS:\n- " + "\n- ".join(lessons) if lessons else "")
                + (f"\n\nCHANGES ASKED FOR THIS VERSION: {notes}" if notes else ""))
        page = llm.ask_text(SYSTEM, user, max_tokens=16000)
        page = clean(page)
        path = os.path.join(tempfile.mkdtemp(prefix="irun-site-"), "draft.html")
        with open(path, "w") as f:
            f.write(page)
        url = db.upload_public(path, f"sites/{cid}/draft.html", content_type="text/plain; charset=utf-8")
    except Exception:
        companies.refund(cid, companies.plans()["costs"]["site"], "website build failed")
        raise
    companies.save(cid, site_status="draft", site_draft_url=url)
    companies.log(cid, "site", "website draft ready for approval", {"draft": url, "bytes": len(page)})
    return url


def clean(page):
    page = re.sub(r"^```(?:html)?\s*|\s*```$", "", page.strip())
    page = re.sub(r"<script\b[^>]*>.*?</script>", "", page, flags=re.S | re.I)  # no scripts on client sites
    page = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", page, flags=re.I)
    if "<html" not in page.lower() or "</html>" not in page.lower():
        raise ValueError("the website came back incomplete")
    return page


def publish(c):
    """Copy an approved draft into the repo (sites/<id>/index.html). The workflow commits it."""
    import requests
    cid = c["id"]
    r = requests.get(c["site_draft_url"], timeout=60)
    r.raise_for_status()
    page = clean(r.text)
    out = os.path.join(ROOT, "sites", cid)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(page)
    url = f"{PAGES}/{cid}/"
    companies.save(cid, site_status="published", site_url=url)
    companies.remember(cid, "decision", f"Website published at {url}.")
    companies.log(cid, "site", "website published", {"url": url})
    return url
