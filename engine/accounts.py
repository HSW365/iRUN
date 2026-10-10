"""Accounts iRun runs content for (HSW365's own brands and paying clients), plus their logins."""
import json
import os

import db

ROOT = os.path.join(os.path.dirname(__file__), "..")
MAIN = "hsw365media"  # the original account: its logins live in GitHub secrets and the un-suffixed token rows
YT_MAIN = "hoodstar365"  # the account GitHub secret YOUTUBE_REFRESH_TOKEN belongs to


def load():
    with open(os.path.join(ROOT, "config", "accounts.json")) as f:
        accts = json.load(f)["accounts"]
    for a in accts:
        p = a.get("products")
        if isinstance(p, str):
            with open(os.path.join(ROOT, p)) as f:
                a["products"] = json.load(f)["products"]
        a.setdefault("platforms", ["tiktok", "instagram"])
        a.setdefault("enabled", True)
        a.setdefault("lead_bot", False)
    return accts


def series(account_id=None):
    """Enabled faceless series (config/series.json), optionally just one account's."""
    path = os.path.join(ROOT, "config", "series.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        rows = json.load(f)["series"]
    return [s for s in rows if s.get("enabled", True) and (account_id is None or s["account"] == account_id)]


def get(account_id):
    return next(a for a in load() if a["id"] == account_id)


def token_name(platform, account_id):
    return platform if account_id == MAIN else f"{platform}:{account_id}"


def _stored(platform, account_id):
    if not db.enabled():
        return None
    try:
        return db.get_token(token_name(platform, account_id))
    except Exception:
        return None


def connected(account_id, platform):
    """(ok, reason). True only when this account can actually publish to this platform."""
    if platform == "tiktok":
        if not (os.environ.get("TIKTOK_CLIENT_KEY") and os.environ.get("TIKTOK_CLIENT_SECRET")):
            return False, "TikTok app keys missing (TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET)"
        st = _stored("tiktok", account_id) or {}
        if st.get("refresh_value") or (account_id == MAIN and os.environ.get("TIKTOK_REFRESH_TOKEN")):
            return True, "connected"
        return False, f"TikTok login not connected for @{account_id} (run engine/tiktok_auth.py --account {account_id})"
    if platform == "instagram":
        if not db.enabled():
            return False, "Instagram needs SUPABASE_SERVICE_KEY (videos must be hosted at a public URL)"
        st = _stored("instagram", account_id) or {}
        if st.get("value") or (account_id == MAIN and os.environ.get("IG_ACCESS_TOKEN")):
            return True, "connected"
        return False, f"Instagram login not connected for @{account_id}"
    if platform == "youtube":
        if not (os.environ.get("YOUTUBE_CLIENT_ID") and os.environ.get("YOUTUBE_CLIENT_SECRET")):
            return False, "YouTube app keys missing (YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET)"
        st = _stored("youtube", account_id) or {}
        if st.get("refresh_value") or (account_id == YT_MAIN and os.environ.get("YOUTUBE_REFRESH_TOKEN")):
            return True, "connected"
        return False, f"YouTube login not connected for @{account_id} (run engine/youtube_auth.py --account {account_id})"
    return False, f"unknown platform {platform}"
