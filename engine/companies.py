"""Companies the Operator runs (Supabase irun_companies), their long-term memory and the live activity log.

An active company is also a content account: accounts.load() merges it in, so the existing promo + faceless
engine makes and posts its videos on the same schedule as the accounts in config/accounts.json.
"""
import datetime as dt
import json
import re
import urllib.parse

import db


def now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    return s[:32] or "company"


# ---------- companies ----------

def all_companies(status=None):
    if not db.enabled():
        return []
    q = "select=*&order=created_at.asc"
    if status:
        q += f"&status=eq.{status}"
    try:
        return db.select("irun_companies", q)
    except Exception as e:  # table missing or offline: the content engine must keep working without the Operator
        print(f"[companies] unavailable: {e}")
        return []


def get(company_id):
    rows = db.select("irun_companies", f"id=eq.{urllib.parse.quote(company_id)}&select=*")
    return rows[0] if rows else None


def save(company_id, **fields):
    fields["updated_at"] = now()
    db.update("irun_companies", {"id": company_id}, fields)


def to_account(c):
    """irun_companies row -> account dict in the config/accounts.json shape."""
    p = c.get("profile") or {}
    handles = c.get("handles") or {}
    handle = (p.get("handle") or handles.get("instagram") or handles.get("tiktok") or "").lstrip("@")
    plan = plan_of(c)
    platforms = list(p.get("platforms") or ["tiktok", "instagram"])
    if plan["name"] in ("Elite", "Comp") and "youtube" not in platforms:
        platforms.append("youtube")
    return {
        "id": c["id"],
        "brand": p.get("brand") or c["name"],
        "handle": handle,
        "type": "company",
        "plan": c.get("plan"),
        "hours": plan["hours"],
        "faceless_ok": plan["faceless"],
        "enabled": c.get("status") == "active" and bool(p.get("products")),
        "platforms": platforms,
        "lead_bot": False,
        "voice": p.get("voice") or "",
        "products": p.get("products") or [],
    }


def to_series(c):
    """The company's faceless series, if its profile has one, in the config/series.json shape."""
    s = (c.get("profile") or {}).get("series")
    if not s or not s.get("cta"):
        return None
    return {"id": s.get("id") or "main", "account": c["id"], "name": s["name"], "enabled": True,
            "style": s.get("style") or "cinematic", "topic": s["topic"], "audience": s["audience"],
            "angles": s.get("angles") or [], "cta": s["cta"]}


# ---------- plans + credits ----------

def plans():
    import os
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "plans.json")) as f:
        return json.load(f)


def plan_of(c):
    """The plan dict for a company. 'comp' (owner-added) companies get Elite features and are never charged."""
    cfg = plans()["plans"]
    return cfg.get(c.get("plan")) or dict(cfg["elite"], name="Comp")


def spend(company_id, amount, reason, ref=None):
    """Take credits. True when covered (comp companies are always covered). Logs the outcome."""
    if amount <= 0:
        return True
    ok = bool(db.rpc("irun_spend_credits", {"p_company": company_id, "p_amount": amount,
                                            "p_reason": reason, "p_ref": ref}))
    if not ok:
        log(company_id, "billing", f"out of credits: skipped {reason}", {"needed": amount})
    return ok


def refund(company_id, amount, reason):
    """Give credits back after work that was paid for failed (returned as purchased credits, which never expire)."""
    c = get(company_id)
    if not c or c.get("plan") == "comp" or amount <= 0:
        return
    save(company_id, bonus_credits=c["bonus_credits"] + amount, credits_used_total=max(0, c["credits_used_total"] - amount))
    db.insert("irun_credit_ledger", {"company_id": company_id, "delta": amount, "reason": f"refund: {reason}"})


# ---------- memory ----------

def remember(company_id, kind, content):
    if not db.enabled() or not content:
        return
    db.insert("irun_memory", {"company_id": company_id, "kind": kind, "content": str(content)[:4000]})


def memories(company_id, limit=60):
    if not db.enabled():
        return []
    return db.select("irun_memory", f"company_id=eq.{urllib.parse.quote(company_id)}"
                                    f"&select=kind,content,created_at&order=created_at.desc&limit={limit}")


def memory_text(company_id, limit=60):
    rows = memories(company_id, limit)
    if not rows:
        return "(nothing yet: this is the first review)"
    return "\n".join(f"- [{r['created_at'][:10]} {r['kind']}] {r['content']}" for r in reversed(rows))


# ---------- live activity ----------

def log(company_id, agent, action, detail=None):
    line = f"[{agent}] {company_id or '-'}: {action}"
    print(line + (f" {json.dumps(detail)[:300]}" if detail else ""))
    if not db.enabled():
        return
    try:
        db.insert("irun_activity", {"company_id": company_id, "agent": agent, "action": action[:500],
                                    "detail": detail})
    except Exception as e:
        print(f"[activity] not logged: {e}")
