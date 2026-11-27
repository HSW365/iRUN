"""HSW365 Army: 100 agents on free infrastructure (GitHub Actions + OpenStreetMap + Supabase).

booking / sales scouts find publicly listed contacts; watchmen check every site; command agents watch money,
posting and outreach and write the shared memory. Nothing here sends email or posts: leads wait in army.html
for the owner to send or approve.
"""
import datetime as dt
import json
import os
import re
import time
import urllib.parse

import requests

import db

ROOT = os.path.join(os.path.dirname(__file__), "..")
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
BAD_RE = re.compile(r"^(no-?reply|donotreply|postmaster|abuse|webmaster|privacy|legal)@|\.(png|jpe?g|gif|webp|svg)$")
LOCAL = ("NJ", "PA", "DE", "NY")
BATCH = int(os.environ.get("ARMY_BATCH", "12"))
BUDGET = int(os.environ.get("ARMY_MINUTES", "40")) * 60


def now():
    return dt.datetime.now(dt.timezone.utc)


def ago(**kw):
    return urllib.parse.quote((now() - dt.timedelta(**kw)).isoformat())


def rows(table, query):
    """All rows, paged past the 1000-row API limit."""
    out = []
    while True:
        page = db.select(table, f"{query}&limit=1000&offset={len(out)}")
        out += page
        if len(page) < 1000:
            return out


def overpass(query):
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": query}, timeout=120,
                              headers={"User-Agent": "HSW365-Army/1.0 (hsw365media@gmail.com)"})
            if r.status_code == 200:
                body = r.json()
                if body.get("remark", "").startswith("runtime error"):
                    raise RuntimeError(body["remark"][:150])
                return body.get("elements", [])
            print(f"  {url} -> {r.status_code}")
        except Exception as e:
            print(f"  {url} failed: {e}")
        time.sleep(4)
    raise RuntimeError("map search is busy; retrying next run")


def scout(a, row, states, blocked):
    state = a.get("state") or states[(a["start"] + row["cursor"]) % len(states)]
    parts = "".join(f'nwr(area.a){f}["{k}"];' for f in a["filters"] for k in ("email", "contact:email"))
    q = f'[out:json][timeout:100];area["ISO3166-2"="US-{state}"][admin_level=4]->.a;({parts});out tags;'
    found = {}
    for el in overpass(q):
        t = el.get("tags", {})
        mail = (t.get("email") or t.get("contact:email") or "").split(";")[0].split(",")[0].strip().lower()
        name = (t.get("name") or "").strip()
        if not name or mail in blocked or not EMAIL_RE.match(mail) or BAD_RE.search(mail):
            continue
        seg = next((t[k] for k in ("amenity", "club", "craft", "shop", "office", "leisure") if t.get(k)), "")
        found[mail] = {"email": mail, "name": name[:140], "kind": a["kind"], "product": a["product"],
                       "segment": seg.replace("_", " ")[:60], "city": t.get("addr:city"), "state": state,
                       "website": t.get("website") or t.get("contact:website"),
                       "phone": t.get("phone") or t.get("contact:phone"), "agent_id": a["id"],
                       "priority": 1 if state in LOCAL else 2}
    new = 0
    if found:
        r = requests.post(f"{db.URL}/rest/v1/army_leads?on_conflict=email", json=list(found.values()), timeout=60,
                          headers=db._h({"Prefer": "return=representation,resolution=ignore-duplicates"}))
        r.raise_for_status()
        new = len(r.json())
    return "ok", f"{state}: {len(found)} contacts, {new} new", new


def watch(a):
    try:
        r = requests.get(a["url"], timeout=40, headers={"User-Agent": "HSW365-Army/1.0"})
        if r.status_code == 200:
            return "ok", f"Online ({r.elapsed.total_seconds():.1f}s)", 0
        return "alert", f"Returned error {r.status_code}: {a['url']}", 0
    except requests.RequestException as e:
        return "alert", f"Unreachable: {a['url']} ({type(e).__name__})", 0


def hours_since(stamp):
    return (now() - dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 3600


def ops(a):
    op = a["op"]
    if op == "money":
        p = db.select("hsw_payments", "status=eq.pending&select=app,amount_cents,method&limit=100")
        if p:
            total = sum(x["amount_cents"] or 0 for x in p) / 100
            apps = ", ".join(sorted({x["app"] for x in p}))
            return "alert", f"{len(p)} payment(s) worth ${total:,.2f} waiting for approval ({apps}). Check the money arrived first.", 0
        return "ok", "No payments waiting", 0
    if op == "posts":
        p = db.select("irun_posts", "status=eq.posted&select=posted_at&order=posted_at.desc.nullslast&limit=1")
        h = hours_since(p[0]["posted_at"]) if p and p[0]["posted_at"] else None
        if h is None or h > 36:
            return "alert", "No Instagram post recorded in " + ("a long time" if h is None else f"{h / 24:.0f} days"), 0
        return "ok", f"Last recorded post {h:.0f}h ago", 0
    if op == "mail":
        p = db.select("irun_sales_log", "kind=eq.sent&select=created_at&order=created_at.desc&limit=1")
        h = hours_since(p[0]["created_at"]) if p else None
        if h is None or h > 36:
            return "alert", "Sales email has not sent in " + ("a long time" if h is None else f"{h / 24:.0f} days"), 0
        return "ok", f"Last sales email {h:.0f}h ago", 0
    if op == "booking":
        bad = []
        for label, f in (("Booking", "contacted_log.json"), ("Offer", "hsw365_offer_contacted_log.json")):
            r = requests.get(f"https://raw.githubusercontent.com/HSW365/booking-outreach-bot/main/data/{f}", timeout=40)
            r.raise_for_status()
            log = r.json()
            sent = sum(1 for x in log if x.get("type") != "send_error")
            errs = [x for x in log if x.get("type") == "send_error"]
            if not sent:
                why = "Gmail rejected the password" if any("535" in x.get("error", "") for x in errs) else "nothing sent yet"
                bad.append(f"{label} bot: 0 sent, {len(errs)} failed ({why})")
        return ("alert", ". ".join(bad), 0) if bad else ("ok", "Both bots are sending", 0)
    if op == "clean":
        stop = {x["email"].lower() for x in rows("irun_suppress", "select=email&order=email")}
        stop |= {x["email"].lower() for x in rows("irun_sales_leads", "status=eq.bounced&select=email&order=email")}
        for e in stop:
            db.update("army_leads", {"email": e}, {"status": "blocked"})
        return "ok", f"{len(stop)} opted-out or bounced addresses blocked", 0
    if op == "local":
        n = len(rows("army_leads", f"kind=eq.booking&status=eq.new&state=in.({','.join(LOCAL)})&select=email&order=email"))
        return "ok", f"{n} local booking contacts ready first", 0
    if op == "video":
        p = db.select("irun_video_jobs", f"status=eq.failed&created_at=gte.{ago(days=2)}&select=id")
        return ("alert", f"{len(p)} member video(s) failed in 48h", 0) if p else ("ok", "Video queue healthy", 0)
    if op == "chief":
        leads = rows("army_leads", "status=eq.new&select=kind&order=email")
        book = sum(1 for x in leads if x["kind"] == "booking")
        alerts = db.select("army_agents", "last_status=eq.alert&id=neq.ops-chief&select=name,last_result&order=id")
        text = f"{book} booking and {len(leads) - book} sales contacts ready. "
        text += "Needs attention: " + " | ".join(f"{x['name']}: {x['last_result']}" for x in alerts) if alerts else "All systems clear."
        return "ok", text, 0
    raise ValueError(op)


def main():
    if not db.enabled():
        raise SystemExit("SUPABASE_SERVICE_KEY missing")
    cfg = json.load(open(os.path.join(ROOT, "config", "agents.json")))
    agents = cfg["agents"]
    r = requests.post(f"{db.URL}/rest/v1/army_agents?on_conflict=id", timeout=60,
                      headers=db._h({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                      json=[{k: a[k] for k in ("id", "name", "squad", "job")} for a in agents])
    r.raise_for_status()
    state = {x["id"]: x for x in db.select("army_agents", "select=*")}
    blocked = {x["email"].lower() for x in rows("irun_suppress", "select=email&order=email")}
    blocked |= {x["email"].lower() for x in rows("irun_sales_leads", "select=email&order=email")}  # already worked by iRun sales
    scouts = sorted((a for a in agents if a["type"] == "scout"),
                    key=lambda a: (state[a["id"]]["last_run_at"] or "", a.get("state") not in LOCAL))[:BATCH]
    order = scouts + [a for a in agents if a["type"] == "watch"] + \
        sorted((a for a in agents if a["type"] == "ops"), key=lambda a: a["op"] == "chief")
    start, done, failed = time.time(), 0, 0
    for a in order:
        if a["type"] == "scout" and time.time() - start > BUDGET:
            continue
        row = state[a["id"]]
        new = 0
        try:
            if a["type"] == "scout":
                status, result, new = scout(a, row, cfg["states"], blocked)
            else:
                status, result, new = watch(a) if a["type"] == "watch" else ops(a)
        except Exception as e:
            status, result = "retry", str(e)[:300]
            failed += 1
        print(f"[{status}] {a['name']}: {result}", flush=True)
        change = {"last_run_at": now().isoformat(), "last_status": status, "last_result": result[:1500],
                  "found_total": row["found_total"] + new}
        if a["type"] == "scout" and status == "ok":
            change["cursor"] = row["cursor"] + 1
        db.update("army_agents", {"id": a["id"]}, change)
        db.insert("army_runs", {"agent_id": a["id"], "status": status, "result": result[:1500]})
        done += 1
        if a["type"] == "scout":
            time.sleep(3)
    print(f"army run complete: {done} agents ran, {failed} will retry")
    if failed == done:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
