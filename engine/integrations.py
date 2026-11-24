"""iRun Connect, engine side (the hub itself is connect.html + supabase/functions/irun-connect).

What the engine does with connected services:
  share_post()    every new Instagram post from your own accounts goes to the Discord / Telegram / Slack channels
                  you switched "Auto-share new posts" on for
  sync()          after each autopilot run: new leads go to the channels with "Lead alerts" on, and to HubSpot when
                  "Sync leads every run" is on
  booking_link()  your Calendly link, when "Add my booking link to Sales Agent emails" is on

Nothing here can stop a post or a run: every failure is printed and saved on that service's card in connect.html.
"""
import datetime as dt

import requests

import db

SHARE = ("discord", "telegram", "slack")
OWN_ACCOUNTS = ("hoodstar365", "hsw365media")  # client company posts are never shared to your channels
UA = {"User-Agent": "HSW365-iRun-Connect/1.0 (hsw365media@gmail.com)"}


def _now():
    return dt.datetime.utcnow().isoformat() + "Z"


def _rows(ids):
    if not db.enabled():
        return []
    try:
        return db.select("irun_integrations", "select=*&status=eq.connected&id=in.(" + ",".join(ids) + ")")
    except Exception as e:  # table missing before the migration runs, network, ...
        print(f"[connect] could not read connected services: {e}")
        return []


def _save(row_id, **fields):
    try:
        db.update("irun_integrations", {"id": row_id}, {**fields, "updated_at": _now()})
    except Exception as e:
        print(f"[connect] could not update {row_id}: {e}")


def _post(url, payload, what):
    r = requests.post(url, json=payload, headers=UA, timeout=30)
    if r.status_code >= 300:
        try:
            j = r.json()
            msg = j.get("description") or j.get("message") or r.text
        except ValueError:
            msg = r.text
        raise RuntimeError(f"{what}: {str(msg)[:200]} (HTTP {r.status_code})")
    return r


def send(row, text, url=None, kind=None, link=None):
    """One message to one connected channel. Same behaviour as SENDERS in the edge function."""
    c = row["creds"]
    extra = url if url and url != link else None
    if row["id"] == "discord":
        content = "\n".join(x for x in (text, link, extra) if x)[:2000]
        _post(c["webhook"] + "?wait=true", {"content": content, "username": "iRun"}, "Discord")
    elif row["id"] == "slack":
        _post(c["webhook"], {"text": "\n".join(x for x in (text, link, extra) if x)[:3800]}, "Slack")
    elif row["id"] == "telegram":
        api = f"https://api.telegram.org/bot{c['token']}"
        cap = "\n\n".join(x for x in (text, link) if x)
        if url and kind in ("video", "image"):
            method, field = ("sendVideo", "video") if kind == "video" else ("sendPhoto", "photo")
            try:
                _post(f"{api}/{method}", {"chat_id": c["chat"], field: url, "caption": cap[:1024]}, "Telegram")
                return
            except Exception:
                pass  # too large to send by URL: fall back to the link
        _post(f"{api}/sendMessage", {"chat_id": c["chat"], "text": "\n\n".join(x for x in (cap, extra) if x)[:4096]}, "Telegram")


def share_post(caption, url=None, kind="video", link=None, account=None):
    """Fan a post that just went live out to every channel with auto-share on. Returns {service: "ok" | error}."""
    if account and account not in OWN_ACCOUNTS:
        return {}
    out = {}
    for row in _rows(SHARE):
        if not row.get("auto_share"):
            continue
        try:
            send(row, caption, url, kind, link)
            out[row["id"]] = "ok"
            if row.get("last_error"):
                _save(row["id"], last_error=None)
        except Exception as e:
            out[row["id"]] = str(e)
            _save(row["id"], last_error=str(e)[:300])
    if out:
        print(f"[connect] shared post: {out}")
    return out


# ---------------------------------------------------------------- leads

def _new_leads(since):
    ig = db.select("irun_leads", f"created_at=gt.{since}&select=username,keyword,product_id,message,created_at&order=created_at.asc&limit=200")
    hot = db.select("irun_sales_leads", "status=in.(hot,needs_owner)&replied_at=gt." + since +
                    "&select=email,business,city,state,status,replied_at&order=replied_at.asc&limit=200")
    return ig, hot


def lead_alerts():
    rows = [r for r in _rows(SHARE) if r.get("lead_alerts")]
    for row in rows:
        meta = row.get("meta") or {}
        since = meta.get("alert_cursor") or (dt.datetime.utcnow() - dt.timedelta(hours=6)).isoformat() + "Z"
        started = _now()
        try:
            ig, hot = _new_leads(since)
        except Exception as e:
            print(f"[connect] lead alerts: could not read leads: {e}")
            return
        lines = [f"@{l['username']} asked about {l.get('product_id') or l.get('keyword') or 'HSW365'} on Instagram"
                 for l in ig if l.get("username")]
        lines += [f"{l['business']}{', ' + l['city'] if l.get('city') else ''} replied to your Sales Agent email"
                  f"{' and wants to talk' if l['status'] == 'hot' else ''}" for l in hot if l.get("business")]
        try:
            if lines:
                head = f"iRun: {len(lines)} new lead{'s' if len(lines) != 1 else ''}"
                body = "\n".join(f"- {x}" for x in lines[:25]) + (f"\n...and {len(lines) - 25} more" if len(lines) > 25 else "")
                send(row, f"{head}\n{body}", link="https://hsw365.github.io/iRUN/dashboard.html")
            _save(row["id"], meta={**meta, "alert_cursor": started}, last_error=None)
        except Exception as e:
            print(f"[connect] lead alert to {row['id']} failed: {e}")
            _save(row["id"], last_error=str(e)[:300])


def _hubspot(token, people):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", **UA}
    clean = lambda p: {k: v for k, v in p.items() if v not in (None, "")}  # noqa: E731
    made = 0
    with_email = [p for p in people if p.get("email")]
    without = [p for p in people if not p.get("email")]
    for i in range(0, len(with_email), 100):
        r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert", headers=h, timeout=60,
                          json={"inputs": [{"idProperty": "email", "id": p["email"], "properties": clean(p)} for p in with_email[i:i + 100]]})
        r.raise_for_status()
        made += len(r.json().get("results", []))
    for i in range(0, len(without), 100):
        r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/batch/create", headers=h, timeout=60,
                          json={"inputs": [{"properties": clean(p)} for p in without[i:i + 100]]})
        r.raise_for_status()
        made += len(r.json().get("results", []))
    return made


def hubspot_sync():
    rows = _rows(("hubspot",))
    if not rows or not (rows[0].get("meta") or {}).get("auto_sync"):
        return
    row = rows[0]
    meta = row.get("meta") or {}
    since = meta.get("last_sync") or (dt.datetime.utcnow() - dt.timedelta(days=30)).isoformat() + "Z"
    started = _now()
    try:
        ig = db.select("irun_leads", f"created_at=gt.{since}&select=username,keyword,product_id&limit=500")
        sales = db.select("irun_sales_leads", f"status=in.(hot,needs_owner,replied)&created_at=gt.{since}"
                          "&select=email,business,contact,city,state,website&limit=500")
        people = [{"firstname": f"@{l['username']}", "lastname": "(Instagram)",
                   "jobtitle": f"Asked about {l.get('product_id') or l.get('keyword') or 'HSW365'}"} for l in ig if l.get("username")]
        for l in sales:
            first, _, last = (l.get("contact") or "").strip().partition(" ")
            people.append({"email": l["email"], "company": l.get("business"), "firstname": first or None, "lastname": last or None,
                           "city": l.get("city"), "state": l.get("state"), "website": l.get("website")})
        n = _hubspot(row["creds"]["token"], people) if people else 0
        _save("hubspot", meta={**meta, "last_sync": started, "synced": int(meta.get("synced") or 0) + n}, last_error=None)
        if n:
            print(f"[connect] HubSpot: {n} leads synced")
    except Exception as e:
        print(f"[connect] HubSpot sync failed: {e}")
        _save("hubspot", last_error=str(e)[:300])


def sync():
    """Run after each autopilot run. Safe to call anytime: it only acts on services you connected and switched on."""
    try:
        lead_alerts()
        hubspot_sync()
    except Exception as e:
        print(f"[connect] sync skipped: {e}")


def booking_link():
    """Calendly scheduling link for Sales Agent emails, only when that switch is on in connect.html."""
    rows = _rows(("calendly",))
    meta = (rows[0].get("meta") or {}) if rows else {}
    link = meta.get("scheduling_url") or ""
    return link if meta.get("use_in_sales") and link.startswith("https://calendly.com/") else ""
