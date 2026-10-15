"""CEO agent: every night it reviews each company, remembers what it learned, and changes what happens next.

It reads the last 7 days (videos made and posted, failures and why, engagement where recorded, outreach results,
credits) plus everything it remembered before, then:
  - writes lessons, decisions and tomorrow's plan to the company's memory
  - rewrites the video angles for each offer and the faceless series ideas (the content engine uses them next)
  - asks for a website rebuild when the site needs it (owner approves before it goes live)
  - lists the things only a human can do (connect a login, add prospects, approve the site)
  - emails the nightly report to the company's contact when email is set up
"""
import datetime as dt
import json
import os

import companies
import db
import llm

SYSTEM = """You are the CEO agent of iRun Operator. You run marketing for one small business on autopilot:
short videos on TikTok/Instagram/YouTube, a one-page website and cold email outreach. Each night you review the
last 7 days and decide what changes tomorrow. You have a memory of earlier nights; keep what worked, drop what did not.

Be concrete and honest. If nothing posted, say so and say why. Never invent numbers; use only the data given.
Angles and ideas must stay inside the business facts (no invented services, prices, claims or stories).
Do not repeat hooks that already ran.

Return ONLY JSON:
{
 "health": "green" | "yellow" | "red",
 "summary": "3-5 sentences for the business owner, plain words",
 "lessons": ["0-4 durable lessons learned from the data"],
 "decisions": ["1-4 decisions you are making now"],
 "plan_tomorrow": ["2-5 concrete things that will happen tomorrow"],
 "angles": {"<offer id>": ["3-6 fresh video angles for that offer"]},
 "faceless_ideas": ["4-8 fresh faceless story ideas for the series"],
 "rebuild_site": false,
 "site_notes": "what to change on the website if rebuild_site is true, else empty",
 "owner_actions": ["things only a human can do, most important first"]
}"""


def since(days):
    return (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"


def snapshot(c):
    cid = c["id"]
    posts = db.select("irun_posts", f"account=eq.{cid}&created_at=gte.{since(7)}"
                                    "&select=platform,product_id,hook,status,error,format,metrics,score,created_at"
                                    "&order=created_at.desc&limit=200")
    pros = db.select("irun_prospects", f"company_id=eq.{cid}&select=status,sends")
    acts = db.select("irun_activity", f"company_id=eq.{cid}&created_at=gte.{since(1)}"
                                      "&select=agent,action,created_at&order=created_at.desc&limit=60")
    by = {}
    for p in posts:
        k = f"{p['platform']}:{p['status']}"
        by[k] = by.get(k, 0) + 1
    errors = sorted({(p.get("error") or "")[:160] for p in posts if p.get("error")})[:8]
    scored = [p for p in posts if p.get("metrics")]
    top = sorted(scored, key=lambda p: p.get("score") or 0, reverse=True)[:5]
    outreach = {}
    for p in pros:
        outreach[p["status"]] = outreach.get(p["status"], 0) + 1
    return {
        "videos_by_platform_status": by,
        "posting_errors": errors,
        "recent_hooks": [p["hook"] for p in posts[:20] if p.get("hook")],
        "best_performing": [{"hook": p["hook"], "platform": p["platform"], "metrics": p["metrics"]} for p in top],
        "engagement_recorded": bool(scored),
        "outreach_prospects_by_status": outreach,
        "credits": {"plan_left": c["credits"], "purchased_left": c["bonus_credits"], "plan": c["plan"]},
        "website": {"status": c["site_status"], "url": c.get("site_url")},
        "last_24h_activity": [a["action"] for a in acts][:40],
    }


def review(c, mode):
    cid, prof = c["id"], c.get("profile") or {}
    companies.log(cid, "ceo", "nightly review started")
    snap = snapshot(c)
    offers = [{"id": p["id"], "name": p["name"], "pitch": p["pitch"], "current_angles": p.get("angles", [])}
              for p in prof.get("products", [])]
    user = (f"BUSINESS: {prof.get('brand') or c['name']}\nSUMMARY: {prof.get('summary')}\n"
            f"FACTS:\n- " + "\n- ".join(prof.get("facts", [])) +
            f"\n\nOFFERS:\n{json.dumps(offers, indent=1)}\n\nFACELESS SERIES: {json.dumps(prof.get('series') or {})}\n"
            f"PLAN: {companies.plan_of(c)['name']} (outreach {'on' if c.get('outreach_enabled') else 'off'})\n"
            f"RUN MODE: {mode}\n\nLAST 7 DAYS:\n{json.dumps(snap, indent=1)}\n\n"
            f"YOUR MEMORY:\n{companies.memory_text(cid)}")
    out = llm.ask_json(SYSTEM, user, max_tokens=4000)

    # act on it: new angles and series ideas feed straight into tomorrow's videos
    ids = {p["id"] for p in prof.get("products", [])}
    for p in prof.get("products", []):
        new = [a for a in (out.get("angles") or {}).get(p["id"], []) if a]
        if new:
            p["angles"] = (new + [a for a in p.get("angles", []) if a not in new])[:8]
    if prof.get("series") and out.get("faceless_ideas"):
        old = prof["series"].get("angles", [])
        prof["series"]["angles"] = (out["faceless_ideas"] + [a for a in old if a not in out["faceless_ideas"]])[:12]
    report = {"at": companies.now(), **{k: out.get(k) for k in
              ("health", "summary", "decisions", "plan_tomorrow", "owner_actions", "lessons")}}
    companies.save(cid, profile=prof, last_review_at=companies.now(), last_report=report)
    for kind in ("lesson", "decision"):
        for line in out.get(kind + "s") or []:
            companies.remember(cid, kind, line)
    if out.get("plan_tomorrow"):
        companies.remember(cid, "plan", " | ".join(out["plan_tomorrow"]))
    companies.remember(cid, "report", f"[{out.get('health')}] {out.get('summary')}")
    companies.log(cid, "ceo", f"review done ({out.get('health')}): {out.get('summary', '')[:160]}",
                  {"decisions": out.get("decisions"), "owner_actions": out.get("owner_actions"),
                   "angles_updated": [k for k in (out.get("angles") or {}) if k in ids]})

    if out.get("rebuild_site") and c["site_status"] == "published":
        companies.remember(cid, "decision", f"Website rebuild: {out.get('site_notes')}")
        report["site_rebuild"] = out.get("site_notes") or "refresh the site"
    email_report(c, report)
    return report


def email_report(c, report):
    to = c.get("email")
    if not (to and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS")):
        return
    import smtplib
    from email.message import EmailMessage
    name = (c.get("profile") or {}).get("brand") or c["name"]
    lines = [f"Your iRun nightly report for {name}", "", report.get("summary") or "", ""]
    for title, key in (("What I decided", "decisions"), ("Tomorrow", "plan_tomorrow"), ("Needs you", "owner_actions")):
        if report.get(key):
            lines += [title + ":"] + [f"- {x}" for x in report[key]] + [""]
    lines += [f"Watch it work live: https://hsw365.github.io/iRUN/client.html?c={c['id']}&k={c['client_key']}", "",
              "iRun by HSW365 Media"]
    msg = EmailMessage()
    msg["From"] = f"iRun <{os.environ['SMTP_USER']}>"
    msg["To"] = to
    msg["Subject"] = f"iRun nightly report: {name} ({report.get('health') or 'ok'})"
    msg.set_content("\n".join(lines))
    try:
        with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465")), timeout=60) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        companies.log(c["id"], "ceo", f"nightly report emailed to {to}")
    except Exception as e:
        companies.log(c["id"], "ceo", f"report email failed: {e}")
