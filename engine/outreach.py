"""Outreach agent: cold email to the company's prospect list, one first email and at most one follow-up.

Prospects come only from lists the owner adds in the dashboard (business contacts; no scraping, no consumers).
Every email carries a working unsubscribe link and the sender's postal address (CAN-SPAM), honors the global
suppression list, stops when someone replies, and stays under the plan's daily cap.

Sends over SMTP (Gmail with an app password works):
  SMTP_USER, SMTP_PASS          the mailbox it sends from (and checks for replies over IMAP)
  SMTP_HOST / SMTP_PORT         default smtp.gmail.com / 465
  IMAP_HOST                     default imap.gmail.com
  OUTREACH_ADDRESS              postal address printed in every email (required to send)
Live sending needs IRUN_MODE=live, the company's outreach switched on in the dashboard, and a plan with outreach.
Otherwise it writes drafts into the activity feed so the owner can read them first.
"""
import datetime as dt
import email.utils
import hashlib
import hmac
import imaplib
import os
import re
import smtplib
import urllib.parse
from email.message import EmailMessage

import companies
import db
import llm

FUNC = "https://lsxdlmrjrcivxwgfkpop.supabase.co/functions/v1/irun-ig-webhook"
FOLLOW_UP_AFTER_DAYS = 4

SYSTEM = """You write short cold emails for a small business to other businesses. You are writing as:
{sender}

What the business offers (only these facts are true; never add any): {offer}
Who it is for: {ideal}
Business facts: {facts}

Rules:
- 60-120 words. Plain text. Sound like a real owner, not a marketer. One clear, low-pressure ask (a reply or a call).
- Personalize with the prospect details given; if none, keep it general. Never pretend you met them or used their
  business. Never invent results, clients, prices, discounts, statistics or deadlines.
- No emojis, no exclamation marks, no links except the website given (if any), no attachments mentioned.
- Do not include a signature block, unsubscribe line or address; those are added after.
{followup}
Return ONLY JSON: {{"subject": "under 50 characters, lowercase is fine, no clickbait", "body": "the email"}}"""

FOLLOWUP = ("- This is the ONE follow-up to an earlier email that got no reply. 30-60 words, reference the earlier "
            "note briefly, make it easy to say no. Subject starts with 'Re: ' plus the earlier subject: {prev}")


def unsub_token(secret, cid, addr):
    return hmac.new(secret.encode(), f"{cid}|{addr.lower()}".encode(), hashlib.sha256).hexdigest()[:32]


def unsub_url(secret, cid, addr):
    q = urllib.parse.urlencode({"view": "unsub", "c": cid, "e": addr.lower(), "t": unsub_token(secret, cid, addr)})
    return f"{FUNC}?{q}"


def setting(key):
    rows = db.select("irun_settings", f"key=eq.{key}&select=value")
    return rows[0]["value"] if rows else None


def smtp_ready():
    return all(os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "OUTREACH_ADDRESS"))


def today_sent(cid):
    since = dt.datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat() + "Z"
    rows = db.select("irun_prospects", f"company_id=eq.{cid}&last_sent_at=gte.{since}&select=id")
    return len(rows)


def due(cid, limit):
    """First emails (status new) then follow-ups (sent once, no reply, 4+ days ago)."""
    new = db.select("irun_prospects", f"company_id=eq.{cid}&status=eq.new&select=*&order=created_at.asc&limit={limit}")
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=FOLLOW_UP_AFTER_DAYS)).isoformat() + "Z"
    fu = db.select("irun_prospects", f"company_id=eq.{cid}&status=eq.sent&sends=eq.1&last_sent_at=lt.{cutoff}"
                                     f"&select=*&order=last_sent_at.asc&limit={limit}")
    return (new + fu)[:limit]


def suppressed(addr):
    return bool(db.select("irun_suppress", f"email=eq.{urllib.parse.quote(addr.lower())}&select=email"))


def write(c, p):
    prof = c.get("profile") or {}
    o = prof.get("outreach") or {}
    site = (prof.get("contact") or {}).get("website") or c.get("site_url") or ""
    follow = FOLLOWUP.format(prev=p.get("last_subject") or "") if p["sends"] >= 1 else ""
    system = SYSTEM.format(sender=o.get("sender") or prof.get("brand") or c["name"], offer=o.get("offer") or prof.get("summary"),
                           ideal=o.get("ideal_customer") or "", facts="; ".join(prof.get("facts", [])[:12]), followup=follow)
    user = (f"Prospect email: {p['email']}\nName: {p.get('name') or '(unknown)'}\nBusiness: {p.get('business') or '(unknown)'}\n"
            f"Note from the owner about them: {p.get('note') or '(none)'}\nWebsite to mention if useful: {site or '(none)'}")
    out = llm.ask_json(system, user, max_tokens=800)
    body = re.sub(r"[^\x00-\x7FÀ-ſ]+", "", out["body"]).strip()
    return out["subject"].strip()[:80], body


def footer(c, secret, addr):
    prof = c.get("profile") or {}
    name = prof.get("brand") or c["name"]
    contact = prof.get("contact") or {}
    lines = [name]
    if contact.get("phone"):
        lines.append(contact["phone"])
    if contact.get("website"):
        lines.append(contact["website"])
    lines += ["", f"{name}, {os.environ.get('OUTREACH_ADDRESS', '')}",
              f"Not interested? One click and you won't hear from us again: {unsub_url(secret, c['id'], addr)}"]
    return "\n".join(lines)


def send(c, p, subject, body, secret):
    prof = c.get("profile") or {}
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((prof.get("brand") or c["name"], user))
    msg["To"] = p["email"]
    reply_to = (prof.get("contact") or {}).get("email") or c.get("email")
    if reply_to and reply_to.lower() != user.lower():
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg["Message-ID"] = email.utils.make_msgid(domain=user.split("@")[-1])
    u = unsub_url(secret, c["id"], p["email"])
    msg["List-Unsubscribe"] = f"<{u}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body + "\n\n" + footer(c, secret, p["email"]))
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(user, os.environ["SMTP_PASS"])
        s.send_message(msg)


def pay_for_email(c):
    """1 credit buys 10 emails. Charge at the start of each block of 10."""
    per = companies.plans()["costs"]["emails_per_credit"]
    fresh = companies.get(c["id"])
    n = fresh["outreach_sent_unbilled"]
    if n == 0 and not companies.spend(c["id"], 1, f"outreach emails (block of {per})"):
        return False
    companies.save(c["id"], outreach_sent_unbilled=(n + 1) % per)
    return True


def check_replies(c):
    """Mark prospects who wrote back as replied (stops follow-ups) and log them as leads. Also catch bounces."""
    if not (os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS")):
        return
    rows = db.select("irun_prospects", f"company_id=eq.{c['id']}&status=in.(sent,followed_up)&select=id,email,last_sent_at")
    if not rows:
        return
    try:
        m = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST", "imap.gmail.com"))
        m.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        m.select("INBOX", readonly=True)
        since = min(r["last_sent_at"] for r in rows)[:10]
        since_imap = dt.date.fromisoformat(since).strftime("%d-%b-%Y")
        for r in rows:
            typ, data = m.search(None, f'(FROM "{r["email"]}" SINCE {since_imap})')
            if typ == "OK" and data and data[0].split():
                db.update("irun_prospects", {"id": r["id"]}, {"status": "replied"})
                companies.log(c["id"], "outreach", f"reply from {r['email']}: follow-ups stopped, answer it in your inbox")
                companies.remember(c["id"], "fact", f"Prospect {r['email']} replied to outreach.")
        typ, data = m.search(None, f'(FROM "mailer-daemon" SINCE {since_imap})')
        if typ == "OK" and data and data[0].split():
            bounced = set()
            for num in data[0].split()[-50:]:
                _, msgdata = m.fetch(num, "(BODY.PEEK[TEXT])")
                text = b"".join(x[1] for x in msgdata if isinstance(x, tuple)).decode("utf-8", "ignore").lower()
                bounced |= {r["email"].lower() for r in rows if r["email"].lower() in text}
            for addr in bounced:
                db.update("irun_prospects", {"company_id": c["id"], "email": addr}, {"status": "bounced"})
                db.insert("irun_suppress", {"email": addr, "reason": "bounced"}, upsert_on="email")
                companies.log(c["id"], "outreach", f"bounced: {addr} (won't be emailed again)")
        m.logout()
    except Exception as e:
        companies.log(c["id"], "outreach", f"could not check the inbox for replies: {e}")


def run(c, mode):
    cid = c["id"]
    plan = companies.plan_of(c)
    if not plan["outreach"]:
        return 0
    live = mode == "live" and c.get("outreach_enabled") and smtp_ready()
    check_replies(c)
    cap = min(plan["outreach_daily_cap"], c.get("outreach_daily_cap") or plan["outreach_daily_cap"])
    room = cap - today_sent(cid) if live else 3
    if room <= 0:
        return 0
    batch = due(cid, room)
    if not batch:
        return 0
    secret = setting("unsub_secret")
    if not secret:
        companies.log(cid, "outreach", "paused: unsub_secret missing in irun_settings")
        return 0
    if not live:
        why = ("IRUN_MODE is draft" if mode != "live" else "outreach is off for this company" if not c.get("outreach_enabled")
               else "SMTP_USER / SMTP_PASS / OUTREACH_ADDRESS not set")
        for p in batch:
            if suppressed(p["email"]):
                continue
            subject, body = write(c, p)
            companies.log(cid, "outreach", f"draft to {p['email']} (not sent: {why})", {"subject": subject, "body": body})
        return 0
    sent = 0
    for p in batch:
        if suppressed(p["email"]):
            db.update("irun_prospects", {"id": p["id"]}, {"status": "unsubscribed"})
            continue
        if not pay_for_email(c):
            break
        followup = p["sends"] >= 1
        try:
            subject, body = write(c, p)
            send(c, p, subject, body, secret)
        except Exception as e:
            db.update("irun_prospects", {"id": p["id"]}, {"error": str(e)[:500]})
            companies.log(cid, "outreach", f"send failed to {p['email']}: {e}")
            continue
        db.update("irun_prospects", {"id": p["id"]}, {
            "status": "followed_up" if followup else "sent", "sends": p["sends"] + 1,
            "last_sent_at": dt.datetime.utcnow().isoformat() + "Z", "last_subject": subject, "error": None})
        companies.log(cid, "outreach", f"emailed {p['email']}" + (" (follow-up)" if followup else ""), {"subject": subject})
        sent += 1
    return sent
