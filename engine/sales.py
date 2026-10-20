"""HSW365 Sales Autopilot: finds U.S. small businesses, emails them the HSW365 offer, answers replies, follows up once,
and mails the owner one nightly summary. Runs on GitHub Actions (.github/workflows/sales.yml), free.

Leads: OpenStreetMap (Overpass API, free, no key) businesses that publish their own email, rotating through every state.
Mail:  SMTP + IMAP with a Gmail app password (SMTP_USER / SMTP_PASS). Replies are answered in the same thread.
Brain: GROQ_API_KEY (free) writes reply answers from the fixed offer facts. Without it, built-in reply templates are used.
Data:  Supabase tables irun_sales_leads, irun_sales_log, and the shared irun_suppress list.

Usage
  python engine/sales.py                  # what this hour calls for (replies every hour)
  python engine/sales.py --task outreach  # outreach | replies | followups | summary | all
"""
import argparse
import datetime as dt
import email
import email.utils
import html
import imaplib
import json
import os
import re
import smtplib
import sys
import time
import urllib.parse
from email.header import decode_header, make_header
from email.message import EmailMessage

import requests

sys.path.insert(0, os.path.dirname(__file__))
import db  # noqa: E402

OWNER = os.environ.get("SALES_OWNER_EMAIL", "hsw365media@gmail.com")
DAILY_CAP = int(os.environ.get("SALES_DAILY_CAP") or 50)
MODE = os.environ.get("SALES_MODE") or "live"
ADDRESS = os.environ.get("OUTREACH_ADDRESS") or "Vineland, NJ"
OUTREACH_UTC_HOUR, FOLLOWUP_UTC_HOUR, SUMMARY_UTC_HOUR = 14, 17, 0
FOLLOW_UP_AFTER_DAYS = 4

LINKS = {
    "calltwin_pdf": "https://hsw365.github.io/calltwin/brochures/CallTwin-HSW365.pdf",
    "queenee_pdf": "https://hsw365.github.io/calltwin/brochures/QUEENEE-HSW365.pdf",
    "calltwin": "https://hsw365.github.io/calltwin/",
    "calltwin_signup": "https://hsw365.github.io/calltwin/signup.html",
    "queenee": "https://hsw365.github.io/queenee/",
    "queenee_pay": "https://buy.stripe.com/aFafZhcdxeQS1822xt3VC0n",
    "store": "https://hsw365.co",
}
PRICES = [
    ("New website or full upgrade", "Mobile-first, built to book jobs, hosting and updates included", "$299 setup + $20/mo"),
    ("CallTwin AI receptionist", "Answers calls, texts and site chat 24/7 and sends every job to your phone",
     "$500 setup, 14 days free, then $99/mo"),
    ("AI Estimates & Proposals", "Photos or video of the job become a finished estimate and proposal, e-sign and deposit",
     "14 days free, then $49/mo"),
    ("Social promotion", "Auto-posts your work to TikTok and Instagram", "from $15/mo"),
    ("All-in bundle", "Website + CallTwin + Estimates & Proposals", "$1,500 + $99/mo"),
]
FACTS = f"""HSW365 Media LLC, veteran-owned, New Jersey. Founder: Elvin Torres Sr.
Products and exact prices (never change them, never discount, never add features):
- QUEENEE website (new site or full upgrade, built from the customer's info, on their own domain): $299 setup + $20/mo. Pay: {LINKS['queenee_pay']}
- CallTwin AI receptionist: answers calls, texts and website chat 24/7, collects caller name, number, address and the job, sends job alerts by text and email to the owner. $500 one-time setup, 14 days free after setup, then plans: Care $49/mo, Pro $99/mo, Managed Business $199/mo. Sign up: {LINKS['calltwin_signup']}
- CallTwin added to a QUEENEE website: $99 on the day of purchase, then $99/mo for 5 months.
- AI Estimates & Proposals add-on: job photos or video become a finished estimate and proposal with e-sign and deposit. 14 days free, then $49/mo.
- Social promotion (auto-posts the business's work to TikTok and Instagram): $15, $35 or $60 a month.
- All-in bundle (website + CallTwin + Estimates & Proposals): $1,500 + $99/mo.
- Brochures: {LINKS['calltwin_pdf']} and {LINKS['queenee_pdf']}
- Other ways to pay: Zelle 856-796-8081, Cash App $hsw365, or {LINKS['store']}"""

STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
          "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
          "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]
CRAFTS = "plumber|hvac|roofer|electrician|carpenter|painter|gardener|builder|tiler|plasterer|stonemason|floorer|" \
         "glaziery|locksmith|cleaning|window_construction|insulation|sweep|handyman|landscaper"
SHOPS = "hairdresser|beauty|car_repair|tyres|florist|bakery|pet_grooming"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
SKIP_LOCAL = re.compile(r"^(no-?reply|donotreply|postmaster|abuse|webmaster|privacy|legal)", re.I)

UNSUB_RE = re.compile(r"\b(unsubscribe|remove me|take me off|stop emailing|do not (contact|email)|don'?t (contact|email)|opt out)\b", re.I)
NO_RE = re.compile(r"\b(not interested|no thanks|no thank you|we'?re (all )?set|we are (all )?set|not at this time|pass on this)\b", re.I)
YES_RE = re.compile(r"^\W*(yes|yeah|yep|sure|interested|i'?m interested|sounds good|let'?s do it|send (it|me|the))\b", re.I)
AUTO_RE = re.compile(r"(out of (the )?office|auto(matic)?[- ]?reply|autoreply|on vacation|away from (the )?office)", re.I)


# ---------------------------------------------------------------- data

def log(kind, email_addr=None, detail=None):
    try:
        db.insert("irun_sales_log", {"kind": kind, "email": email_addr, "detail": (detail or "")[:2000]})
    except Exception as e:
        print("log failed:", e)
    print(f"[{kind}] {email_addr or ''} {detail or ''}"[:300])


def setting(key, default=None):
    rows = db.select("irun_settings", f"key=eq.{key}&select=value")
    return rows[0]["value"] if rows else default


def set_setting(key, value):
    db.insert("irun_settings", {"key": key, "value": str(value)}, upsert_on="key")


def lead(addr):
    rows = db.select("irun_sales_leads", f"email=eq.{urllib.parse.quote(addr.lower(), safe='')}&select=*")
    return rows[0] if rows else None


def save(addr, **fields):
    db.update("irun_sales_leads", {"email": addr.lower()}, fields)


def suppressed(addr):
    return bool(db.select("irun_suppress", f"email=eq.{urllib.parse.quote(addr.lower(), safe='')}&select=email"))


def suppress(addr, reason):
    db.insert("irun_suppress", {"email": addr.lower(), "reason": reason}, upsert_on="email")


def add_leads(rows):
    """Insert new leads, never touching ones that already exist."""
    if not rows:
        return 0
    r = requests.post(f"{db.URL}/rest/v1/irun_sales_leads?on_conflict=email",
                      headers=db._h({"Prefer": "return=representation,resolution=ignore-duplicates"}), json=rows, timeout=60)
    r.raise_for_status()
    return len(r.json())


def sent_today():
    since = dt.datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat() + "Z"
    return len(db.select("irun_sales_log", f"kind=eq.sent&created_at=gte.{since}&select=id"))


# ---------------------------------------------------------------- leads

def overpass(query):
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": query}, timeout=200,
                              headers={"User-Agent": "HSW365-iRun/1.0 (hsw365media@gmail.com)"})
            if r.status_code == 200:
                return r.json().get("elements", [])
            print(f"overpass {url} -> {r.status_code}")
        except Exception as e:
            print(f"overpass {url} failed: {e}")
        time.sleep(5)
    return []


def find_in_state(state):
    q = (f'[out:json][timeout:180];area["ISO3166-2"="US-{state}"][admin_level=4]->.a;('
         f'nwr(area.a)["craft"~"^({CRAFTS})$"]["email"];nwr(area.a)["craft"~"^({CRAFTS})$"]["contact:email"];'
         f'nwr(area.a)["shop"~"^({SHOPS})$"]["email"];nwr(area.a)["shop"~"^({SHOPS})$"]["contact:email"];'
         f'nwr(area.a)["office"~"^(construction_company|contractor)$"]["email"];'
         f'nwr(area.a)["office"~"^(construction_company|contractor)$"]["contact:email"];);out tags;')
    out, seen = [], set()
    for el in overpass(q):
        t = el.get("tags", {})
        raw = (t.get("email") or t.get("contact:email") or "").split(";")[0].strip().lower()
        name = (t.get("name") or "").strip()
        if not raw or not name or raw in seen or not EMAIL_RE.match(raw) or SKIP_LOCAL.match(raw.split("@")[0]):
            continue
        seen.add(raw)
        trade = (t.get("craft") or t.get("shop") or t.get("office") or "local business").replace("_", " ")
        out.append({"email": raw, "business": name[:120], "trade": trade[:60], "city": (t.get("addr:city") or "")[:80] or None,
                    "state": state, "source": "openstreetmap"})
    return out


def stock_leads(need):
    """Make sure at least `need` fresh leads are waiting, pulling from the next states in rotation."""
    have = len(db.select("irun_sales_leads", "status=eq.new&select=email&limit=1000"))
    idx = int(setting("sales_state_idx", "0") or 0)
    tries = 0
    while have < need and tries < 6:
        state = STATES[idx % len(STATES)]
        rows = [r for r in find_in_state(state) if not suppressed(r["email"])]
        added = add_leads(rows)
        log("leads", None, f"{state}: {len(rows)} found, {added} new")
        have += added
        idx += 1
        tries += 1
        set_setting("sales_state_idx", idx)
    return have


# ---------------------------------------------------------------- mail

def smtp_ready():
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


LAST = ' style="background:#f4f4f6"'


def price_table():
    rows = "".join(
        f'<tr{LAST if i == len(PRICES) - 1 else ""}><td style="padding:10px;border-bottom:1px solid #e5e5e5">'
        f'<b>{html.escape(n)}</b><br><span style="color:#666">{html.escape(d)}</span></td>'
        f'<td style="padding:10px;border-bottom:1px solid #e5e5e5;text-align:right;white-space:nowrap"><b>{html.escape(p)}</b></td></tr>'
        for i, (n, d, p) in enumerate(PRICES))
    return ('<table style="width:100%;border-collapse:collapse;font-size:14px;margin:18px 0">'
            '<tr style="background:#111;color:#fff"><td style="padding:10px">Service</td><td style="padding:10px;text-align:right">Price</td></tr>'
            f'{rows}</table>')


def wrap(inner):
    return ('<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;color:#111;font-size:15px;line-height:1.55">'
            f'{inner}<p>Elvin Torres Sr.<br>Founder, HSW365 Media LLC &middot; Veteran-owned<br>'
            f'<a href="{LINKS["store"]}">hsw365.co</a></p>'
            f'<p style="font-size:12px;color:#888;border-top:1px solid #eee;padding-top:10px">HSW365 Media LLC, {html.escape(ADDRESS)}. '
            'Not interested? Reply "unsubscribe" and you won\'t hear from me again.</p></div>')


def text_version(h):
    t = re.sub(r"<br\s*/?>", "\n", h)
    t = re.sub(r"</(p|tr|div)>", "\n", t)
    t = re.sub(r"<td[^>]*>", "  ", t)
    t = re.sub(r"<a href=\"([^\"]+)\"[^>]*>[^<]*</a>", r"\1", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


TRADE_WORDS = {"plumber": "plumbing", "roofer": "roofing", "electrician": "electrical", "gardener": "landscaping",
               "landscaper": "landscaping", "hairdresser": "salon", "car repair": "auto repair", "tyres": "tire",
               "builder": "construction", "construction company": "construction", "contractor": "contracting",
               "hvac": "HVAC", "carpenter": "carpentry", "painter": "painting", "tiler": "tile", "floorer": "flooring",
               "glaziery": "glass", "window construction": "window", "sweep": "chimney", "pet grooming": "pet grooming",
               "local business": "local"}


def first_email(l):
    who = html.escape((l.get("contact") or "").strip() or f"{l['business']} team")
    trade = TRADE_WORDS.get((l.get("trade") or "").lower(), l.get("trade") or "local")
    where = f" in {l['city']}" if l.get("city") else ""
    inner = (f"<p>Hi {who},</p>"
             f"<p>I'm Elvin Torres Sr., founder of HSW365 Media. I build websites and AI tools for {html.escape(trade)} "
             f"businesses like {html.escape(l['business'])}{html.escape(where)}.</p>"
             "<p>Jobs go to whoever answers first. <b>CallTwin</b> is an AI receptionist that answers every call, text and "
             "website chat 24/7, captures the customer's name, number, address and job, and sends it straight to your phone. "
             "Pair it with a new website that's built to book work.</p>"
             f"{price_table()}"
             f'<p>Full details: <a href="{LINKS["calltwin_pdf"]}">CallTwin brochure</a> &middot; '
             f'<a href="{LINKS["queenee_pdf"]}">Website brochure</a></p>'
             f"<p>Reply <b>\"YES\"</b> and I'll send a free written estimate and proposal for {html.escape(l['business'])}. "
             "No cost, no obligation.</p>")
    return f"{l['business']} — never miss another job call", wrap(inner)


def followup_email(l):
    inner = (f"<p>Hi {html.escape((l.get('contact') or '').strip() or l['business'] + ' team')},</p>"
             "<p>Following up on my note about answering every call and getting a website that books jobs. "
             "Both brochures with full pricing:</p>"
             f'<p><a href="{LINKS["calltwin_pdf"]}">CallTwin AI receptionist</a><br>'
             f'<a href="{LINKS["queenee_pdf"]}">Websites</a></p>'
             "<p>If it's a fit, reply \"YES\" and I'll send your free estimate and proposal. If not, no problem.</p>")
    return "Re: " + (l.get("last_subject") or f"{l['business']} — never miss another job call"), wrap(inner)


def send(to, subject, body_html, in_reply_to=None):
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr(("Elvin Torres Sr. | HSW365 Media", user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=False)
    mid = email.utils.make_msgid(domain=user.split("@")[-1])
    msg["Message-ID"] = mid
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=unsubscribe>"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(text_version(body_html))
    msg.add_alternative(body_html, subtype="html")
    host, port = os.environ.get("SMTP_HOST") or "smtp.gmail.com", int(os.environ.get("SMTP_PORT") or 465)
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(user, os.environ["SMTP_PASS"])
        s.send_message(msg)
    return mid


# ---------------------------------------------------------------- outreach

def outreach():
    room = DAILY_CAP - sent_today()
    if room <= 0:
        return 0
    stock_leads(room)
    batch = db.select("irun_sales_leads", f"status=eq.new&select=*&order=created_at.asc&limit={room}")
    sent = 0
    for l in batch:
        if suppressed(l["email"]):
            save(l["email"], status="unsubscribed")
            continue
        subject, body = first_email(l)
        if MODE != "live":
            log("draft", l["email"], subject)
            continue
        try:
            mid = send(l["email"], subject, body)
        except smtplib.SMTPDataError as e:
            log("send_error", l["email"], f"stopping run, sending limit or block: {e}")
            break
        except Exception as e:
            save(l["email"], error=str(e)[:500], status="bounced")
            log("send_error", l["email"], str(e))
            continue
        save(l["email"], status="sent", sends=1, last_sent_at=dt.datetime.utcnow().isoformat() + "Z",
             last_subject=subject, message_id=mid, error=None)
        log("sent", l["email"], subject)
        sent += 1
        time.sleep(20)
    return sent


def followups():
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=FOLLOW_UP_AFTER_DAYS)).isoformat() + "Z"
    due = db.select("irun_sales_leads", f"status=eq.sent&sends=eq.1&last_sent_at=lt.{cutoff}&select=*&limit=60")
    n = 0
    for l in due:
        if suppressed(l["email"]):
            save(l["email"], status="unsubscribed")
            continue
        subject, body = followup_email(l)
        if MODE != "live":
            log("draft", l["email"], subject)
            continue
        try:
            send(l["email"], subject, body, in_reply_to=l.get("message_id"))
        except Exception as e:
            log("send_error", l["email"], str(e))
            continue
        save(l["email"], status="followed_up", sends=2, last_sent_at=dt.datetime.utcnow().isoformat() + "Z")
        log("followup", l["email"], subject)
        n += 1
        time.sleep(20)
    return n


# ---------------------------------------------------------------- replies

def header_text(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def body_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                h = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                return html.unescape(re.sub(r"<[^>]+>", " ", h))
        return ""
    return (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "ignore")


def fresh_text(t):
    """The new part of a reply, without the quoted thread."""
    lines = []
    for line in t.splitlines():
        if re.match(r"^\s*>", line) or re.match(r"^\s*On .+wrote:\s*$", line) or re.match(r"^-{2,}\s*Original Message", line, re.I) \
                or re.match(r"^\s*From:\s", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()[:3000]


def groq_answer(l, text):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    system = ("You answer replies to a cold email for HSW365 Media as Elvin Torres Sr. Use ONLY these facts; never invent "
              "prices, discounts, features, timelines, guarantees or results:\n" + FACTS +
              "\n\nReturn only JSON: {\"intent\": \"yes\" | \"question\" | \"owner\", \"reply_html\": \"...\"}.\n"
              "intent=owner when they ask for anything the facts can't answer (custom work, other prices, contracts, "
              "complaints, payment problems, a meeting time) - then reply_html is empty.\n"
              "For yes: a short written estimate and proposal: what they get, the matching prices, the next step and the "
              "right pay or signup link, and ask for business name, domain if they have one, and best callback number.\n"
              "For question: answer it in 2-5 short sentences, then invite a YES.\n"
              "reply_html: simple <p> paragraphs, no signature, no unsubscribe line, no emojis, no exclamation marks.")
    user = f"Business: {l.get('business')} ({l.get('trade')}, {l.get('city') or ''} {l.get('state') or ''})\nTheir reply:\n{text}"
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), "temperature": 0.3,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                          timeout=60)
        r.raise_for_status()
        out = json.loads(r.json()["choices"][0]["message"]["content"])
        if out.get("intent") not in ("yes", "question", "owner"):
            return None
        return out
    except Exception as e:
        print("groq failed:", e)
        return None


def proposal_html(l):
    return (f"<p>Thanks for the reply. Here's your estimate and proposal for {html.escape(l.get('business') or 'your business')}.</p>"
            f"{price_table()}"
            "<p><b>Next step</b><br>"
            f'Website: <a href="{LINKS["queenee_pay"]}">start here</a> ($299 setup + $20/mo)<br>'
            f'CallTwin: <a href="{LINKS["calltwin_signup"]}">sign up here</a> ($500 setup, 14 days free, then $99/mo)<br>'
            "Prefer another way to pay? Zelle 856-796-8081 or Cash App $hsw365.</p>"
            "<p>Reply with your business name, your domain if you have one, and the best number to reach you, "
            "and I'll get your setup started.</p>")


def question_html(l):
    return ("<p>Thanks for getting back to me. Here's the full breakdown:</p>"
            f"{price_table()}"
            f'<p>More detail: <a href="{LINKS["calltwin_pdf"]}">CallTwin brochure</a> &middot; '
            f'<a href="{LINKS["queenee_pdf"]}">Website brochure</a></p>'
            "<p>Reply \"YES\" with the best number to reach you and I'll put together your proposal.</p>")


def handle_reply(l, msg, text):
    addr = l["email"]
    subject = header_text(msg.get("Subject")) or l.get("last_subject") or "Your HSW365 proposal"
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    mid = msg.get("Message-ID")
    save(addr, replied_at=dt.datetime.utcnow().isoformat() + "Z", last_reply=text[:2000])
    if UNSUB_RE.search(text) or NO_RE.search(text):
        save(addr, status="unsubscribed")
        suppress(addr, "unsubscribed by reply")
        log("unsubscribed", addr, text[:200])
        return
    if AUTO_RE.search(subject + " " + text[:300]):
        log("auto_reply", addr, subject)
        return
    ai = groq_answer(l, text)
    if ai and ai["intent"] == "owner":
        save(addr, status="needs_owner")
        log("needs_owner", addr, text[:300])
        return
    if ai and ai.get("reply_html"):
        body, intent = ai["reply_html"], ai["intent"]
    elif YES_RE.search(text):
        body, intent = proposal_html(l), "yes"
    else:
        body, intent = question_html(l), "question"
    if MODE != "live":
        log("draft_reply", addr, f"{intent}: {subject}")
        return
    send(addr, subject, wrap(body), in_reply_to=mid)
    save(addr, status="hot", answered_at=dt.datetime.utcnow().isoformat() + "Z")
    log("answered", addr, f"{intent}: {text[:200]}")


def replies():
    if not smtp_ready():
        print("replies: SMTP_USER / SMTP_PASS not set")
        return 0
    m = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST") or "imap.gmail.com")
    m.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
    m.select("INBOX")
    since = (dt.date.today() - dt.timedelta(days=3)).strftime("%d-%b-%Y")
    typ, data = m.search(None, f"(SINCE {since})")
    done = {r["detail"] for r in db.select("irun_sales_log", "kind=eq.seen&select=detail&order=id.desc&limit=2000")}
    n = 0
    for num in (data[0].split() if typ == "OK" and data else [])[-300:]:
        _, raw = m.fetch(num, "(BODY.PEEK[])")
        if not raw or not isinstance(raw[0], tuple):
            continue
        msg = email.message_from_bytes(raw[0][1])
        mid = (msg.get("Message-ID") or "").strip()
        if not mid or mid in done:
            continue
        sender = email.utils.parseaddr(msg.get("From"))[1].lower()
        text = body_text(msg)
        if "mailer-daemon" in sender or "postmaster" in sender:
            for l in db.select("irun_sales_leads", "status=in.(sent,followed_up)&select=email&order=last_sent_at.desc&limit=500"):
                if l["email"] in text.lower():
                    save(l["email"], status="bounced")
                    suppress(l["email"], "bounced")
                    log("bounced", l["email"])
            log("seen", None, mid)
            continue
        l = lead(sender)
        if not l or l["status"] in ("unsubscribed", "bounced"):
            continue
        try:
            handle_reply(l, msg, fresh_text(text) or text[:2000])
            n += 1
        except Exception as e:
            log("reply_error", sender, str(e))
            continue
        log("seen", sender, mid)
    m.logout()
    return n


# ---------------------------------------------------------------- summary

def summary():
    since = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat() + "Z"
    rows = db.select("irun_sales_log", f"created_at=gte.{since}&select=kind,email,detail&order=id.asc&limit=5000")
    count = lambda k: sum(1 for r in rows if r["kind"] == k)  # noqa: E731
    hot = [r for r in rows if r["kind"] == "answered"]
    owner = [r for r in rows if r["kind"] == "needs_owner"]
    errors = [r for r in rows if r["kind"] in ("send_error", "reply_error")]
    total = len(db.select("irun_sales_leads", "status=neq.new&select=email&limit=100000"))
    lines = [f"<p><b>Last 24 hours</b><br>Emails sent: {count('sent')}<br>Follow-ups: {count('followup')}<br>"
             f"Replies answered: {len(hot)}<br>Unsubscribed: {count('unsubscribed')}<br>Bounced: {count('bounced')}<br>"
             f"Businesses contacted all-time: {total}</p>"]
    if hot:
        lines.append("<p><b>Hot leads</b><br>" + "<br>".join(html.escape(f"{r['email']}: {r['detail'][:120]}") for r in hot) + "</p>")
    if owner:
        lines.append("<p><b>Needs you</b><br>" + "<br>".join(html.escape(f"{r['email']}: {r['detail'][:160]}") for r in owner) + "</p>")
    if errors:
        lines.append(f"<p><b>Errors</b>: {len(errors)} (latest: {html.escape(errors[-1]['detail'][:160])})</p>")
    body = '<div style="font-family:Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6">' + "".join(lines) + "</div>"
    if smtp_ready():
        send(OWNER, f"HSW365 Autopilot — {dt.date.today():%b %d}", body)
    log("summary", OWNER, text_version(body)[:500])


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="auto", choices=["auto", "outreach", "replies", "followups", "summary", "all"])
    a = ap.parse_args()
    if not db.enabled():
        sys.exit("Sales autopilot needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
    if not smtp_ready():
        print("SMTP_USER / SMTP_PASS not set: finding leads and writing drafts only")
    hour = dt.datetime.utcnow().hour
    t = a.task
    print(f"=== HSW365 Sales Autopilot === mode={MODE} task={t} cap={DAILY_CAP} groq={'set' if os.environ.get('GROQ_API_KEY') else 'off'}")
    if t in ("auto", "replies", "all"):
        try:
            print("replies answered:", replies())
        except Exception as e:
            log("reply_error", None, f"inbox check failed: {e}")
    if t in ("outreach", "all") or (t == "auto" and hour == OUTREACH_UTC_HOUR):
        if smtp_ready():
            print("emails sent:", outreach())
        else:
            stock_leads(DAILY_CAP)
    if t in ("followups", "all") or (t == "auto" and hour == FOLLOWUP_UTC_HOUR):
        if smtp_ready():
            print("follow-ups sent:", followups())
    if t in ("summary", "all") or (t == "auto" and hour == SUMMARY_UTC_HOUR):
        summary()
    print("sales autopilot done")


if __name__ == "__main__":
    main()
