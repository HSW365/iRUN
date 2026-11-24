"""HSW365 Elite orders: intake in -> demo website built -> emailed to the customer for approval or revision.

Customers fill elite.html after buying. The row lands in Supabase irun_elite_orders. This engine (run every 10 minutes by
.github/workflows/elite.yml) picks up orders that are 'new' or 'revision', builds a one-page demo from the owner's own
answers (nothing invented), saves it to the order, commits a copy to sites/elite/<id8>/index.html, and emails the
customer a review link (elite-review.html) with Approve / Request changes. Elvin gets a copy of every email.

  python engine/elite.py            # process the queue
  python engine/elite.py --mail-test
"""
import datetime as dt
import email.utils
import html
import json
import os
import smtplib
import sys
from email.message import EmailMessage

import db
import llm
import website

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PAGES = "https://hsw365.github.io/iRUN"
OWNER = os.environ.get("ELITE_OWNER_EMAIL", "hsw365media@gmail.com")

SYSTEM = website.SYSTEM + """
This is an HSW365 Elite build: the top tier. Aim well above a template. A distinctive visual idea per business, large
confident type, precise spacing, a restrained palette taken from the owner's stated colors or chosen to suit the trade.
If the owner gave social handles, show them as plain text links in the footer (instagram.com/<handle> style URLs are
fine). If they gave a domain, show it in the footer text. No form elements (there is no backend): use tel:, mailto: and the
given links for calls to action. If a phone or email is missing, make the call to action "Get in touch" pointing to a
mailto: link only if an email was provided, otherwise a link to the first social handle given.
"""


def mail(to, subject, body_html, cc=None):
    user = os.environ.get("SMTP_USER")
    if not (user and os.environ.get("SMTP_PASS")):
        print(f"[elite] mail not configured, would send to {to}: {subject}")
        return False
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr(("Elvin Torres Sr. | HSW365 Media", user))
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Reply-To"] = OWNER
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg.set_content("Open this email in an HTML-capable client, or reply to hsw365media@gmail.com.")
    msg.add_alternative(body_html, subtype="html")
    host, port = os.environ.get("SMTP_HOST") or "smtp.gmail.com", int(os.environ.get("SMTP_PORT") or 465)
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(user, os.environ["SMTP_PASS"])
        s.send_message(msg, to_addrs=[to] + ([cc] if cc else []))
    return True


def wrap(inner):
    return ('<div style="background:#0a0a0f;padding:28px 12px"><div style="max-width:560px;margin:auto;background:#14141d;'
            'border:1px solid #2a2a38;border-radius:8px;padding:30px;font:16px/1.6 -apple-system,Segoe UI,Arial,sans-serif;color:#e8e8ef">'
            f'{inner}<p style="color:#8f8f9f;font-size:13px;margin-top:28px">HSW365 Media LLC &middot; 19 12th, Apt 2, Hammonton, NJ 08037 '
            '&middot; reply to this email any time.</p></div></div>')


def brief(o):
    i = o.get("intake") or {}
    parts = {
        "business": o["business"], "owner_name": o["name"], "email": o["email"], "phone": o.get("phone") or "",
        "domain_owned": i.get("domain_have", ""), "domains_wanted": i.get("domain_want", ""),
        "social_handles": i.get("socials") or {}, "about": i.get("about", ""), "services": i.get("services", ""),
        "area_served": i.get("area", ""), "look_and_feel": i.get("style", ""), "other_links": i.get("links", ""),
        "notes": i.get("notes", ""),
    }
    return json.dumps({k: v for k, v in parts.items() if v}, indent=1)


def build_one(o):
    oid = o["id"]
    db.update("irun_elite_orders", {"id": oid}, {"status": "building", "updated_at": dt.datetime.utcnow().isoformat() + "Z"})
    revising = o["status"] == "revision" and o.get("demo_html")
    user = "Build the demo website for this Elite customer.\n\nCUSTOMER DETAILS:\n" + brief(o)
    if revising:
        user += ("\n\nTHE CURRENT DEMO (revise it, keep what the customer did not ask to change):\n" + o["demo_html"][:60000]
                 + "\n\nCHANGES THE CUSTOMER ASKED FOR:\n" + (o.get("revision_notes") or ""))
    page = website.clean(llm.ask_text(SYSTEM, user, max_tokens=16000))
    version = (o.get("version") or 0) + 1
    out = os.path.join(ROOT, "sites", "elite", oid[:8])
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(page)
    db.update("irun_elite_orders", {"id": oid}, {
        "status": "demo_ready", "demo_html": page, "version": version, "error": None,
        "demo_path": f"sites/elite/{oid[:8]}/", "updated_at": dt.datetime.utcnow().isoformat() + "Z"})
    link = f"{PAGES}/elite-review.html?o={oid}&k={o['key']}"
    name = html.escape(o["name"].split()[0] if o["name"].strip() else "there")
    biz = html.escape(o["business"])
    if revising:
        lead = f"Your updated demo for <b>{biz}</b> is ready (version {version}), built from the changes you asked for."
    else:
        lead = f"Your Elite website demo for <b>{biz}</b> is ready. It's built from the details you gave us."
    body = wrap(
        f'<p style="margin:0 0 14px">Hi {name},</p><p>{lead}</p>'
        f'<p style="margin:22px 0"><a href="{link}" style="background:#f5b800;color:#0a0a0f;font-weight:700;text-decoration:none;'
        'padding:14px 24px;border-radius:3px;display:inline-block">Review your demo</a></p>'
        '<p>On that page you can <b>approve</b> it, or <b>request changes</b> in your own words and we rebuild it. '
        'There is no limit on rounds until it is right.</p><p>Elvin Torres Sr.<br>HSW365 Media</p>')
    mail(o["email"], f"Your {o['business']} website demo is ready", body, cc=OWNER)
    print(f"[elite] {oid[:8]} {o['business']}: demo v{version} ready")
    return True


def notify_owner(subject, inner):
    try:
        mail(OWNER, subject, wrap(inner))
    except Exception as e:
        print(f"[elite] owner mail failed: {e}")


def approved_notices():
    """Tell Elvin once when a customer approves."""
    for o in db.select("irun_elite_orders", "status=eq.approved&select=*"):
        hist = o.get("history") or []
        if any(h.get("event") == "owner_notified" for h in hist):
            continue
        notify_owner(f"APPROVED: {o['business']} approved their Elite demo",
                     f"<p><b>{html.escape(o['business'])}</b> ({html.escape(o['name'])}, {html.escape(o['email'])}) approved version "
                     f"{o.get('version')}. Demo: {PAGES}/sites/elite/{o['id'][:8]}/</p>"
                     "<p>Next: launch on their domain and collect the balance.</p>")
        hist.append({"at": dt.datetime.utcnow().isoformat() + "Z", "event": "owner_notified"})
        db.update("irun_elite_orders", {"id": o["id"]}, {"history": hist})


def intake_notices():
    for o in db.select("irun_elite_orders", "status=eq.new&select=*"):
        hist = o.get("history") or []
        if o["email"].lower().endswith("@example.com") or any(h.get("event") == "intake_notified" for h in hist):
            continue
        i = o.get("intake") or {}
        notify_owner(f"NEW ELITE INTAKE: {o['business']}",
                     f"<p><b>{html.escape(o['business'])}</b> from {html.escape(o['name'])} &lt;{html.escape(o['email'])}&gt; "
                     f"{html.escape(o.get('phone') or '')}, order {html.escape(o.get('order_ref') or '?')}.</p>"
                     f"<p>Domain owned: {html.escape(i.get('domain_have') or '-')}<br>Domains wanted: {html.escape(i.get('domain_want') or '-')}<br>"
                     f"Socials: {html.escape(json.dumps(i.get('socials') or {}))}</p><p>Demo build is starting.</p>")
        hist.append({"at": dt.datetime.utcnow().isoformat() + "Z", "event": "intake_notified"})
        db.update("irun_elite_orders", {"id": o["id"]}, {"history": hist})
        o["history"] = hist


def main():
    if not db.enabled():
        print("[elite] Supabase not configured"); return
    # a build that died mid-run goes back in the queue after 30 minutes
    cutoff = (dt.datetime.utcnow() - dt.timedelta(minutes=30)).isoformat() + "Z"
    for o in db.select("irun_elite_orders", f"status=eq.building&updated_at=lt.{cutoff}&select=id"):
        db.update("irun_elite_orders", {"id": o["id"]}, {"status": "new"})
    intake_notices()
    queue = db.select("irun_elite_orders", "status=in.(new,revision)&select=*&order=updated_at.asc&limit=5")
    if queue and not llm.available():
        print("[elite] ANTHROPIC_API_KEY missing: demos cannot be built")
        notify_owner("Elite demo waiting: no builder key", f"<p>{len(queue)} Elite order(s) are waiting but the ANTHROPIC_API_KEY secret is not set on the iRUN repo.</p>")
        return
    queue = [o for o in queue if not o["email"].lower().endswith("@example.com")]  # test submissions
    for o in queue:
        try:
            build_one(o)
        except Exception as e:
            print(f"[elite] {o['id'][:8]} failed: {e}")
            db.update("irun_elite_orders", {"id": o["id"]}, {"status": "failed", "error": str(e)[:500]})
            notify_owner(f"Elite demo FAILED: {o['business']}", f"<p>{html.escape(str(e)[:400])}</p><p>Order {o['id']}</p>")
    approved_notices()


if __name__ == "__main__":
    main()
