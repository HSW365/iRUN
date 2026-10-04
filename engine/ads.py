"""Paid ads: move Meta (Facebook / Instagram) ad budget toward the ad sets that are performing.

For an account with an "ads" block in config/accounts.json, iRun reads the last 7 days for every active ad set
in the listed campaigns and shifts daily budget from weak ad sets to strong ones.

Guardrails (money is involved, so these are fixed in code):
  - Total daily budget across the ad sets never goes up. iRun only moves money between them.
  - No ad set moves more than max_shift_pct (default 20%) in one day, so Meta's learning phase isn't reset.
  - Ad sets that spent under min_spend in the window are left alone: not enough data to judge.
  - Nothing changes unless IRUN_ADS_MODE=live. The default is a dry run that only writes the proposal.
  - iRun never creates campaigns, never raises spend and never touches campaigns you didn't list.

Ranking: return on ad spend when Meta reports purchases for the ad set, otherwise click-through rate.

Account config:
  "ads": {"ad_account_id": "act_123", "campaign_ids": ["1201..."], "max_shift_pct": 20, "min_spend": 5}
Secret: META_ADS_TOKEN (a system-user token with ads_management on that ad account).
"""
import datetime as dt
import json
import os

import requests

GRAPH = "https://graph.facebook.com/v23.0"
ROOT = os.path.join(os.path.dirname(__file__), "..")
INTEL = os.path.join(ROOT, "content", "intel")
MIN_BUDGET = 100  # minor units ($1.00): Meta's floor for most currencies


def rebalance(adsets, max_shift=0.20, min_spend=5.0, min_budget=MIN_BUDGET):
    """adsets: [{"id","name","daily_budget"(minor units),"spend","roas","ctr"}].
    Returns [{"id","name","from","to","metric","value"}] for ad sets whose budget should change."""
    judged = [a for a in adsets if a.get("daily_budget") and float(a.get("spend") or 0) >= min_spend]
    if len(judged) < 2:
        return []
    metric = "roas" if any(float(a.get("roas") or 0) > 0 for a in judged) else "ctr"
    scores = [max(float(a.get(metric) or 0), 0.0) for a in judged]
    if sum(scores) <= 0:
        return []
    total = sum(int(a["daily_budget"]) for a in judged)
    deltas = []
    for a, s in zip(judged, scores):
        old = int(a["daily_budget"])
        target = total * s / sum(scores)
        step = max(-max_shift * old, min(max_shift * old, target - old))
        deltas.append(max(min_budget, old + step) - old)
    ups, downs = sum(d for d in deltas if d > 0), -sum(d for d in deltas if d < 0)
    if ups > downs:  # winners can only take what the others actually gave up, so total spend never rises
        deltas = [d * downs / ups if d > 0 else d for d in deltas]
    new = [int(int(a["daily_budget"]) + d) for a, d in zip(judged, deltas)]  # rounding down keeps the total at or under
    return [{"id": a["id"], "name": a.get("name"), "from": int(a["daily_budget"]), "to": n, "metric": metric,
             "value": round(float(a.get(metric) or 0), 3)}
            for a, n in zip(judged, new) if n != int(a["daily_budget"])]


def _get(path, tok, **params):
    r = requests.get(f"{GRAPH}/{path}", params={**params, "access_token": tok}, timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Meta Ads: {data['error'].get('message', data['error'])}")
    return data


def fetch_adsets(campaign_ids, tok):
    out = []
    for cid in campaign_ids:
        sets = _get(f"{cid}/adsets", tok, fields="id,name,daily_budget,effective_status", limit=100).get("data", [])
        for s in sets:
            if s.get("effective_status") != "ACTIVE" or not s.get("daily_budget"):
                continue  # paused, or the campaign sets the budget (Advantage campaign budget): Meta handles those
            ins = _get(f"{s['id']}/insights", tok, date_preset="last_7d",
                       fields="spend,impressions,clicks,ctr,purchase_roas").get("data", [])
            i = ins[0] if ins else {}
            roas = next((float(x["value"]) for x in i.get("purchase_roas") or [] if x.get("value")), 0.0)
            out.append({"id": s["id"], "name": s.get("name"), "campaign_id": cid, "daily_budget": int(s["daily_budget"]),
                        "spend": float(i.get("spend") or 0), "impressions": int(i.get("impressions") or 0),
                        "clicks": int(i.get("clicks") or 0), "ctr": float(i.get("ctr") or 0), "roas": roas})
    return out


def apply(changes, tok):
    for c in changes:
        r = requests.post(f"{GRAPH}/{c['id']}", data={"daily_budget": c["to"], "access_token": tok}, timeout=60).json()
        c["applied"] = bool(r.get("success"))
        if not c["applied"]:
            c["error"] = str(r.get("error", r))[:300]


def run(acct, mode=None):
    """Returns the report dict (also written to content/intel/<account>-ads.json), or None if ads aren't set up."""
    cfg = acct.get("ads") or {}
    tok = os.environ.get("META_ADS_TOKEN")
    if not cfg.get("campaign_ids"):
        return None
    if not tok:
        print(f"[ads] @{acct['id']}: META_ADS_TOKEN is not set; skipping")
        return None
    mode = mode or os.environ.get("IRUN_ADS_MODE", "dry-run")
    adsets = fetch_adsets(cfg["campaign_ids"], tok)
    changes = rebalance(adsets, float(cfg.get("max_shift_pct", 20)) / 100, float(cfg.get("min_spend", 5)))
    if mode == "live":
        apply(changes, tok)
    report = {"account": acct["id"], "ran_at": dt.datetime.utcnow().isoformat() + "Z", "mode": mode,
              "window": "last 7 days", "adsets": adsets, "changes": changes,
              "total_daily_budget": sum(a["daily_budget"] for a in adsets)}
    os.makedirs(INTEL, exist_ok=True)
    with open(os.path.join(INTEL, f"{acct['id']}-ads.json"), "w") as f:
        json.dump(report, f, indent=1)
    verb = "moved" if mode == "live" else "would move"
    print(f"[ads] @{acct['id']}: {len(adsets)} ad sets, {verb} budget on {len(changes)} ({mode})")
    return report
