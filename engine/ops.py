"""iRun Operator: runs whole businesses on autopilot, the way Polsia does, on top of the iRun content engine.

Agents
  onboard   website/handles -> business profile (engine/onboard.py)
  site      profile -> one-page website, published after owner approval (engine/website.py)
  content   the existing video engine (engine/run.py) posts for every active company on its plan's slots
  outreach  cold email to the company's prospect list, replies and bounces tracked (engine/outreach.py)
  ceo       nightly review: memory, new angles, plan, report (engine/ceo.py)

Runs hourly from .github/workflows/operator.yml:
  every hour   onboard new companies, build first websites, publish approved websites
  14:xx UTC    outreach (10am ET)
  03:xx UTC    CEO review (11pm ET)

Usage
  python engine/ops.py                                   # what this hour calls for
  python engine/ops.py --task ceo --company acmeplumbing
  python engine/ops.py --add "Acme Plumbing" --url acmeplumbing.com --handle instagram=acmeplumbing
"""
import argparse
import datetime as dt
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import companies  # noqa: E402
import db  # noqa: E402
import llm  # noqa: E402

CEO_HOUR = 3
OUTREACH_HOUR = 14


def sync_plans():
    cfg = companies.plans()
    db.insert("irun_settings", {"key": "plans", "value": json.dumps(cfg)}, upsert_on="key")
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "owners.json")) as f:
        owners = [e.lower() for e in json.load(f)["emails"]]
    db.insert("irun_settings", {"key": "owner_emails", "value": json.dumps(owners)}, upsert_on="key")


def add(name, url=None, handles=None, notes=None, email=None, plan="comp"):
    base = companies.slug(name)
    cid, n = base, 2
    taken = {c["id"] for c in companies.all_companies()}
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "accounts.json")) as f:
        taken |= {a["id"] for a in json.load(f)["accounts"]}
    while cid in taken:
        cid, n = f"{base}{n}", n + 1
    db.insert("irun_companies", {"id": cid, "name": name, "source_url": url, "handles": handles or {}, "notes": notes,
                                 "email": email, "plan": plan, "status": "pending"})
    companies.log(cid, "operator", f"company added: {name}")
    return cid


def zelle_expiry():
    """Zelle customers pay month by month. 3 days after the paid month ends with no renewal, pause the autopilot."""
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=3)).isoformat() + "Z"
    for c in companies.all_companies("active"):
        if c.get("pay_method") == "zelle" and c.get("plan") != "comp" and c.get("paid_until") and c["paid_until"] < cutoff:
            companies.save(c["id"], status="paused", credits=0)
            companies.log(c["id"], "billing", "month ended without a Zelle renewal: autopilot paused. Renew from your page to restart.")


def onboard_pending(only=None):
    import onboard
    import website
    for c in companies.all_companies("pending"):
        if only and c["id"] != only:
            continue
        try:
            onboard.onboard(c)
            c = companies.get(c["id"])
            if c["site_status"] == "none":
                website.build(c)
        except Exception as e:
            traceback.print_exc()
            companies.save(c["id"], status="error", error=str(e)[:1000])
            companies.log(c["id"], "onboard", f"failed: {e}")


def sites(only=None):
    import website
    for c in companies.all_companies("active"):
        if only and c["id"] != only:
            continue
        try:
            if c["site_status"] == "approved":
                website.publish(c)
            elif c["site_status"] == "none" and c.get("profile"):
                website.build(c)
        except Exception as e:
            traceback.print_exc()
            companies.log(c["id"], "site", f"failed: {e}")


def outreach_all(mode, only=None):
    import outreach
    for c in companies.all_companies("active"):
        if only and c["id"] != only:
            continue
        try:
            n = outreach.run(c, mode)
            if n:
                companies.log(c["id"], "outreach", f"{n} emails sent today")
        except Exception as e:
            traceback.print_exc()
            companies.log(c["id"], "outreach", f"failed: {e}")


def ceo_all(mode, only=None):
    import ceo
    import website
    for c in companies.all_companies("active"):
        if only and c["id"] != only:
            continue
        try:
            rep = ceo.review(c, mode)
            if rep.get("site_rebuild"):
                website.build(companies.get(c["id"]), rep["site_rebuild"])
        except Exception as e:
            traceback.print_exc()
            companies.log(c["id"], "ceo", f"review failed: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="auto", choices=["auto", "onboard", "site", "outreach", "ceo", "all"])
    ap.add_argument("--company")
    ap.add_argument("--mode", default=os.environ.get("IRUN_MODE", "draft"), choices=["draft", "live"])
    ap.add_argument("--add", metavar="NAME", help="add a company (owner comp plan) and onboard it now")
    ap.add_argument("--url")
    ap.add_argument("--handle", action="append", default=[], help="platform=handle, repeatable")
    ap.add_argument("--notes")
    ap.add_argument("--email")
    a = ap.parse_args()
    if not db.enabled():
        sys.exit("Operator needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
    if not llm.available():
        sys.exit("Operator needs ANTHROPIC_API_KEY (its agents think with Claude)")
    print(f"=== iRun Operator === mode={a.mode} task={a.task} smtp={'set' if os.environ.get('SMTP_USER') else 'MISSING'}")
    sync_plans()

    if a.add:
        handles = dict(h.split("=", 1) for h in a.handle if "=" in h)
        a.company = add(a.add, a.url, handles, a.notes, a.email)
        a.task = "onboard"

    hour = dt.datetime.utcnow().hour
    t = a.task
    if t == "auto":
        zelle_expiry()
    if t in ("auto", "onboard", "all"):
        onboard_pending(a.company)
    if t in ("auto", "site", "all"):
        sites(a.company)
    if t in ("outreach", "all") or (t == "auto" and hour == OUTREACH_HOUR):
        outreach_all(a.mode, a.company)
    if t in ("ceo", "all") or (t == "auto" and hour == CEO_HOUR):
        ceo_all(a.mode, a.company)
    print("operator done")


if __name__ == "__main__":
    main()
