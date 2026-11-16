"""iRun Fundraise: an AI that runs a founder's fundraising. Deck review, matched investors with scores, outreach, meetings.

The founder signs up (fundraise plan), pastes or uploads the deck on raise.html, describes the raise, and imports the
investor list they want worked (CSV or paste). Every hour iRun:

  deck      reviews a requested deck: readiness score, slide-by-slide fixes, a rewritten one-liner and narrative (1 credit)
  match     scores every investor against the raise (stage, check size, sector, geography) and says why
  draft     writes a personal first email for each strong match, from the deck and the investor's own fields only
  send      sends the emails the founder approved (first email + one follow-up after 4 days), CAN-SPAM footer, daily cap
  replies   marks investors who wrote back, catches bounces, and logs them so the founder can book the meeting

Nothing is invented: only facts in the deck, the founder's notes and the investor's own row go into an email. Nothing is
sent until the founder approves that investor and switches sending on. 10 emails = 1 credit (same as Operator outreach).

  python engine/fundraise.py                      every task for every fundraise company
  python engine/fundraise.py --task deck          deck | match | draft | send | replies | all
  python engine/fundraise.py --company acme       one company
  python engine/fundraise.py --mode live          draft (default: never sends) | live (sends approved emails)
"""
import argparse
import datetime as dt
import email.utils
import hashlib
import imaplib
import json
import os
import re
import sys
import traceback
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import companies  # noqa: E402
import db  # noqa: E402
import llm  # noqa: E402
import outreach  # noqa: E402

STAGES = ["pre-seed", "seed", "series-a", "series-b", "growth"]
DRAFT_MIN_SCORE = 60
DRAFTS_PER_RUN = 12
FOLLOW_UP_AFTER_DAYS = 4
DEFAULT_DAILY_CAP = 15
GENERALIST = {"generalist", "agnostic", "sector agnostic", "sector-agnostic", "all", "any", "multi-sector", "diversified"}


def now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def eligible(c):
    return bool(companies.plan_of(c).get("fundraise")) or c.get("plan") == "comp"


def campaign(cid):
    rows = db.select("irun_fund_campaigns", f"company_id=eq.{urllib.parse.quote(cid)}&select=*")
    return rows[0] if rows else None


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ---------- deck review ----------

DECK_SYSTEM = """You are the deck doctor of iRun Fundraise. You review a startup pitch deck the way a sharp seed investor
would, then tell the founder exactly what to fix so an investor says yes to a meeting.

Hard rules:
- Judge and rewrite only from the deck text and the founder's notes. Never invent traction, revenue, customers, team
  credentials, market sizes, partnerships or any number. If a slide needs a fact that is missing, write the exact
  placeholder "[add: what is missing]" and list it under missing.
- Be direct and specific. No flattery. Say what an investor will doubt.
- Score honestly: most early decks land 35-70.
- No emojis.

Return ONLY JSON:
{
 "readiness_score": 0-100,
 "verdict": "2-3 sentences: is this deck ready to send, and the one thing that matters most",
 "strengths": ["2-5 real strengths"],
 "gaps": ["3-7 biggest gaps, most important first"],
 "slides": [ {"slide": "Problem | Solution | Product | Market | Traction | Business model | Go to market | Competition | Team | Ask | Other", "score": 0-10, "feedback": "what is wrong or missing, 1-2 sentences", "rewrite": "a stronger version of this slide's headline and main points using only given facts"} ],
 "one_liner": "a rewritten one-line pitch, under 25 words",
 "narrative": "a rewritten 120-180 word investor pitch in plain words",
 "investor_questions": ["5-8 questions investors will ask this founder"],
 "missing": ["facts the founder must add before sending, e.g. monthly revenue, number of customers"]
}"""


def review_deck(c, camp):
    cid = c["id"]
    if not llm.available():
        companies.log(cid, "fundraise", "deck review is waiting: ANTHROPIC_API_KEY is not set on the engine")
        return False
    if not (camp.get("deck_text") or "").strip():
        db.update("irun_fund_campaigns", {"company_id": cid}, {"review_status": "failed", "review_error": "No deck text yet. Paste it or upload the PDF."})
        return False
    if not companies.spend(cid, 1, "fundraise: deck review"):
        db.update("irun_fund_campaigns", {"company_id": cid}, {"review_status": "failed", "review_error": "Out of credits. Add a few and request the review again."})
        return False
    user = (f"Startup: {camp.get('startup') or c['name']}\nStage: {camp.get('stage') or '(not given)'}\n"
            f"Raising: {camp.get('raise_usd') or '(not given)'} USD\nSectors: {', '.join(camp.get('sectors') or []) or '(not given)'}\n"
            f"One-liner from the founder: {camp.get('one_liner') or '(none)'}\nTraction notes from the founder: {camp.get('traction') or '(none)'}\n\n"
            f"DECK TEXT:\n{(camp['deck_text'] or '')[:60000]}")
    try:
        rv = llm.ask_json(DECK_SYSTEM, user, max_tokens=6000)
        rv["readiness_score"] = max(0, min(100, int(rv.get("readiness_score") or 0)))
    except Exception as e:
        companies.refund(cid, 1, "fundraise: deck review failed")
        db.update("irun_fund_campaigns", {"company_id": cid}, {"review_status": "failed", "review_error": str(e)[:300]})
        companies.log(cid, "fundraise", f"deck review failed, credit refunded: {e}"[:300])
        return False
    db.update("irun_fund_campaigns", {"company_id": cid}, {"review_status": "done", "review": rv, "review_at": now(), "review_error": None})
    companies.log(cid, "fundraise", f"deck reviewed: readiness {rv['readiness_score']}/100, {len(rv.get('gaps') or [])} gaps to fix")
    companies.remember(cid, "fact", f"Deck review {now()[:10]}: readiness {rv['readiness_score']}/100. Gaps: " + "; ".join((rv.get("gaps") or [])[:3]))
    return True


# ---------- matching ----------

def camp_hash(camp):
    keys = ("stage", "raise_usd", "check_usd", "sectors", "geo")
    return hashlib.sha256(json.dumps([camp.get(k) for k in keys], sort_keys=True, default=str).encode()).hexdigest()[:16]


def stage_idx(s):
    s = norm(s).replace(" ", "-")
    return STAGES.index(s) if s in STAGES else None


def score(camp, inv):
    """0-100 fit of one investor to the raise, with the reasons shown to the founder. Deterministic and explainable."""
    pts, why = 0, []
    # stage (30)
    ci, ist = stage_idx(camp.get("stage")), [x for x in (stage_idx(s) for s in inv.get("stages") or []) if x is not None]
    if not ist:
        pts += 10; why.append("stage focus not listed")
    elif ci is None:
        pts += 10
    elif ci in ist:
        pts += 30; why.append(f"invests at {camp['stage']}")
    elif min(abs(ci - i) for i in ist) == 1:
        pts += 14; why.append("invests one stage away")
    else:
        why.append("stage mismatch")
    # check size (25)
    target = camp.get("check_usd") or (camp.get("raise_usd") // 5 if camp.get("raise_usd") else None)
    lo, hi = inv.get("check_min"), inv.get("check_max")
    if target and (lo or hi):
        lo, hi = lo or 0, hi or 10 ** 12
        if lo <= target <= hi:
            pts += 25; why.append("check size fits")
        elif target * 2 >= lo and target <= hi * 2:
            pts += 12; why.append("check size is close")
        else:
            why.append("check size mismatch")
    else:
        pts += 10
    # sector (30)
    mine = {norm(s) for s in camp.get("sectors") or [] if norm(s)}
    theirs = {norm(s) for s in inv.get("sectors") or [] if norm(s)}
    if not theirs or theirs & {norm(g) for g in GENERALIST}:
        pts += 15; why.append("sector focus open")
    elif not mine:
        pts += 10
    else:
        hit = {m for m in mine if any(m in t or t in m for t in theirs)}
        if hit:
            pts += 30 if len(hit) >= min(2, len(mine)) else 24
            why.append("backs " + ", ".join(sorted(hit)[:3]))
        else:
            why.append("sector mismatch")
    # geography (15)
    geo, loc = norm(camp.get("geo")), norm(inv.get("location"))
    if not loc:
        pts += 7
    elif not geo or "global" in loc or "worldwide" in loc or any(w in loc for w in geo.split() if len(w) > 2):
        pts += 15; why.append("location fits")
    else:
        pts += 3; why.append("different region")
    return min(100, pts), why


def match_company(c, camp):
    cid = c["id"]
    h = camp_hash(camp)
    invs = db.select("irun_investors", f"company_id=eq.{urllib.parse.quote(cid)}&select=*&limit=5000")
    have = {m["investor_id"]: m for m in db.select("irun_fund_matches", f"company_id=eq.{urllib.parse.quote(cid)}&select=id,investor_id,status&limit=10000")}
    rescore = camp.get("match_hash") != h
    done = 0
    for inv in invs:
        m = have.get(inv["id"])
        if m and not rescore:
            continue
        sc, why = score(camp, inv)
        if m:
            db.update("irun_fund_matches", {"id": m["id"]}, {"score": sc, "reasons": why, "updated_at": now()})
        else:
            db.insert("irun_fund_matches", {"company_id": cid, "investor_id": inv["id"], "score": sc, "reasons": why})
        done += 1
    if rescore:
        db.update("irun_fund_campaigns", {"company_id": cid}, {"match_hash": h})
    if done:
        companies.log(cid, "fundraise", f"matched {done} investors against your raise")
    return done


# ---------- drafting ----------

DRAFT_SYSTEM = """You write a short first email from a startup founder to one investor. You are writing as:
{sender}

The startup (only these facts are true; never add any): {startup}
One-liner: {one_liner}
Traction and facts from the founder: {traction}
Raising: {raise_line}
Booking link (use it for the ask when given): {booking}

Rules:
- 80-130 words. Plain text. Sound like a founder, not a marketer. One clear, low-pressure ask: a 15-minute call.
- Personalize from the investor fields given (firm, role, sectors, stage focus, note). Say why this investor fits in one
  sentence. Never claim to know their portfolio or past deals unless it is in the note. Never pretend you met.
- Never invent traction, customers, revenue, valuation, growth figures, investors already committed or deadlines.
  If there is no traction fact, do not mention traction.
- No emojis, no exclamation marks, no attachments mentioned, no links except the booking link.
- No signature block, unsubscribe line or address; those are added after.
{followup}
Return ONLY JSON: {{"subject": "under 55 characters, no clickbait", "body": "the email"}}"""

FOLLOWUP = ("- This is the ONE follow-up to an earlier email that got no reply. 30-55 words, reference the earlier note "
            "briefly, make it easy to say no. Subject: Re: {prev}")


def write_email(c, camp, inv, follow_prev=None):
    prof = c.get("profile") or {}
    sender = f"{c.get('name')}'s founder" if not camp.get("startup") else f"the founder of {camp['startup']}"
    system = DRAFT_SYSTEM.format(
        sender=sender, startup=camp.get("startup") or prof.get("summary") or c["name"],
        one_liner=camp.get("one_liner") or (camp.get("review") or {}).get("one_liner") or "(none)",
        traction=(camp.get("traction") or "(none given)")[:1200],
        raise_line=(f"${camp['raise_usd']:,} {camp.get('stage') or ''} round".strip() if camp.get("raise_usd") else "(not stated)"),
        booking=camp.get("booking_url") or "(none: ask them to reply with a time)",
        followup=FOLLOWUP.format(prev=follow_prev or "") if follow_prev is not None else "")
    user = (f"Investor name: {inv['name']}\nFirm: {inv.get('firm') or '(unknown)'}\nRole: {inv.get('role') or '(unknown)'}\n"
            f"Type: {inv.get('type')}\nStage focus: {', '.join(inv.get('stages') or []) or '(unknown)'}\n"
            f"Sector focus: {', '.join(inv.get('sectors') or []) or '(unknown)'}\nLocation: {inv.get('location') or '(unknown)'}\n"
            f"Note from the founder about this investor: {inv.get('note') or '(none)'}")
    out = llm.ask_json(system, user, max_tokens=700)
    body = re.sub(r"[^\x00-\x7FÀ-ſ]+", "", out["body"]).strip()
    return out["subject"].strip()[:80], body


def draft_company(c, camp):
    cid = c["id"]
    if not llm.available():
        return 0
    rows = db.select("irun_fund_matches",
                     f"company_id=eq.{urllib.parse.quote(cid)}&status=eq.matched&score=gte.{DRAFT_MIN_SCORE}"
                     f"&select=id,investor_id,score&order=score.desc&limit={DRAFTS_PER_RUN}")
    n = 0
    for m in rows:
        inv = db.select("irun_investors", f"id=eq.{m['investor_id']}&select=*")
        if not inv or not inv[0].get("email"):
            continue  # no email on file: stays a match the founder can reach another way
        try:
            subject, body = write_email(c, camp, inv[0])
        except Exception as e:
            db.update("irun_fund_matches", {"id": m["id"]}, {"error": str(e)[:300]})
            companies.log(cid, "fundraise", f"could not draft for {inv[0]['name']}: {e}"[:300])
            continue
        db.update("irun_fund_matches", {"id": m["id"]}, {"status": "drafted", "subject": subject, "body": body, "error": None, "updated_at": now()})
        n += 1
    if n:
        companies.log(cid, "fundraise", f"{n} investor emails drafted and waiting for your approval")
    return n


# ---------- sending ----------

def today_sent(cid):
    since = dt.datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat() + "Z"
    return len(db.select("irun_fund_matches", f"company_id=eq.{urllib.parse.quote(cid)}&last_sent_at=gte.{since}&select=id"))


def send_company(c, camp, mode):
    cid = c["id"]
    plan = companies.plan_of(c)
    live = mode == "live" and camp.get("send_enabled") and outreach.smtp_ready()
    cap = int(plan.get("fundraise_daily_cap") or DEFAULT_DAILY_CAP)
    room = cap - today_sent(cid)
    if room <= 0:
        return 0
    secret = outreach.setting("unsub_secret")
    if not secret:
        companies.log(cid, "fundraise", "sending paused: unsub_secret missing in irun_settings")
        return 0
    q = urllib.parse.quote(cid)
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=FOLLOW_UP_AFTER_DAYS)).isoformat() + "Z"
    first = db.select("irun_fund_matches", f"company_id=eq.{q}&status=eq.approved&select=*&order=score.desc&limit={room}")
    follow = db.select("irun_fund_matches", f"company_id=eq.{q}&status=eq.sent&sends=eq.1&last_sent_at=lt.{cutoff}&select=*&limit={room}")
    batch = (first + follow)[:room]
    if not batch:
        return 0
    if not live:
        why = ("IRUN_MODE is draft" if mode != "live" else "sending is switched off on your page" if not camp.get("send_enabled")
               else "SMTP_USER / SMTP_PASS / OUTREACH_ADDRESS not set on the engine")
        companies.log(cid, "fundraise", f"{len(batch)} approved emails are ready but not sent: {why}")
        return 0
    sent = 0
    for m in batch:
        inv = db.select("irun_investors", f"id=eq.{m['investor_id']}&select=*")
        if not inv or not inv[0].get("email"):
            continue
        inv = inv[0]
        if outreach.suppressed(inv["email"]):
            db.update("irun_fund_matches", {"id": m["id"]}, {"status": "unsubscribed", "updated_at": now()})
            continue
        follow_up = m["sends"] >= 1
        if not outreach.pay_for_email(c):
            companies.log(cid, "fundraise", "out of credits: sending paused until you add credits")
            break
        try:
            if follow_up:
                subject, body = write_email(c, camp, inv, follow_prev=m.get("subject") or "")
            else:
                subject, body = m["subject"], m["body"]
            outreach.send(c, {"email": inv["email"]}, subject, body, secret)
        except Exception as e:
            db.update("irun_fund_matches", {"id": m["id"]}, {"error": str(e)[:300]})
            companies.log(cid, "fundraise", f"send failed to {inv['name']}: {e}"[:300])
            continue
        db.update("irun_fund_matches", {"id": m["id"]}, {
            "status": "followed_up" if follow_up else "sent", "sends": m["sends"] + 1, "last_sent_at": now(),
            "subject": subject if follow_up else m["subject"], "error": None, "updated_at": now()})
        companies.log(cid, "fundraise", f"emailed {inv['name']}" + (f" at {inv['firm']}" if inv.get("firm") else "") + (" (follow-up)" if follow_up else ""),
                      {"subject": subject, "score": m["score"]})
        sent += 1
    return sent


# ---------- replies and bounces ----------

def check_replies(c):
    cid = c["id"]
    if not (os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS")):
        return 0
    rows = db.select("irun_fund_matches", f"company_id=eq.{urllib.parse.quote(cid)}&status=in.(sent,followed_up)&select=id,investor_id,last_sent_at")
    if not rows:
        return 0
    invs = {i["id"]: i for i in db.select("irun_investors", f"company_id=eq.{urllib.parse.quote(cid)}&select=id,name,firm,email&limit=5000")}
    found = 0
    try:
        m = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST") or "imap.gmail.com")
        m.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        m.select("INBOX", readonly=True)
        since = dt.date.fromisoformat(min(r["last_sent_at"] for r in rows)[:10]).strftime("%d-%b-%Y")
        for r in rows:
            inv = invs.get(r["investor_id"])
            if not inv or not inv.get("email"):
                continue
            typ, data = m.search(None, f'(FROM "{inv["email"]}" SINCE {since})')
            if typ == "OK" and data and data[0].split():
                db.update("irun_fund_matches", {"id": r["id"]}, {"status": "replied", "replied_at": now(), "updated_at": now()})
                companies.log(cid, "fundraise", f"{inv['name']} replied: follow-ups stopped. Answer in your inbox and book the meeting.")
                companies.remember(cid, "fact", f"Investor {inv['name']} ({inv.get('firm') or 'no firm'}) replied to fundraising outreach.")
                found += 1
        typ, data = m.search(None, f'(FROM "mailer-daemon" SINCE {since})')
        if typ == "OK" and data and data[0].split():
            bounced = set()
            for num in data[0].split()[-50:]:
                _, msgdata = m.fetch(num, "(BODY.PEEK[TEXT])")
                text = b"".join(x[1] for x in msgdata if isinstance(x, tuple)).decode("utf-8", "ignore").lower()
                bounced |= {i["email"].lower() for i in invs.values() if i.get("email") and i["email"].lower() in text}
            for r in rows:
                inv = invs.get(r["investor_id"])
                if inv and inv.get("email") and inv["email"].lower() in bounced:
                    db.update("irun_fund_matches", {"id": r["id"]}, {"status": "bounced", "updated_at": now()})
                    db.insert("irun_suppress", {"email": inv["email"].lower(), "reason": "bounced"}, upsert_on="email")
                    companies.log(cid, "fundraise", f"bounced: {inv['email']} (won't be emailed again)")
        m.logout()
    except Exception as e:
        companies.log(cid, "fundraise", f"could not check the inbox for replies: {e}"[:300])
    return found


# ---------- run ----------

def work(c, task, mode):
    camp = campaign(c["id"])
    if not camp:
        return "no campaign yet"
    out = []
    if task in ("deck", "all") and camp.get("review_status") == "requested":
        out.append(f"deck={'ok' if review_deck(c, camp) else 'no'}")
        camp = campaign(c["id"])
    if task in ("match", "all"):
        out.append(f"matched={match_company(c, camp)}")
    if task in ("draft", "all"):
        out.append(f"drafted={draft_company(c, camp)}")
    if task in ("replies", "all"):
        out.append(f"replies={check_replies(c)}")
    if task in ("send", "all"):
        out.append(f"sent={send_company(c, camp, mode)}")
    return " ".join(out) or "nothing to do"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="all", choices=["all", "deck", "match", "draft", "send", "replies"])
    ap.add_argument("--company")
    ap.add_argument("--mode", default=os.environ.get("IRUN_MODE", "draft"), choices=["draft", "live"])
    a = ap.parse_args()
    if not db.enabled():
        sys.exit("Fundraise needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
    print(f"=== iRun Fundraise === task={a.task} mode={a.mode}")
    for c in companies.all_companies("active"):
        if (a.company and c["id"] != a.company) or not eligible(c):
            continue
        try:
            print(f"[{c['id']}] {work(c, a.task, a.mode)}")
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
