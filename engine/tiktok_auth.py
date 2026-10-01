"""One-time TikTok login for an iRun account (HSW365's own or a client's). Run on your PC:
    set TIKTOK_CLIENT_KEY=...   set TIKTOK_CLIENT_SECRET=...
    (optional, to save the login straight into iRun)  set SUPABASE_URL=...  set SUPABASE_SERVICE_KEY=...
    python engine/tiktok_auth.py --account hsw365media
Open the printed link, have the account owner approve, copy the code shown on the callback page, paste it here.
With the Supabase variables set, the login is saved for that account and iRun rotates it from then on.
Without them, the refresh token is printed: for hsw365media put it in GitHub secret TIKTOK_REFRESH_TOKEN.
"""
import argparse
import os
import secrets
import sys
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(__file__))
import accounts  # noqa: E402
import db  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--account", default=accounts.MAIN, help="account id from config/accounts.json")
a = ap.parse_args()
accounts.get(a.account)  # fail early on a typo

REDIRECT = os.environ.get("TIKTOK_REDIRECT_URI", "https://hsw365.github.io/iRUN/callback.html")
ck, cs = os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"]
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": ck, "scope": "user.info.basic,video.publish", "response_type": "code",
    "redirect_uri": REDIRECT, "state": secrets.token_urlsafe(12)})
print(f"\nLog in as @{a.account} and approve:\n\n" + url + "\n")
code = urllib.parse.unquote(input("Paste the code: ").strip())
r = requests.post("https://open.tiktokapis.com/v2/oauth/token/",
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  data={"client_key": ck, "client_secret": cs, "code": code,
                        "grant_type": "authorization_code", "redirect_uri": REDIRECT}, timeout=30).json()
if "refresh_token" not in r:
    raise SystemExit(f"Failed: {r}")
print("open_id =", r.get("open_id"), " scopes =", r.get("scope"))
if db.enabled():
    db.set_token(accounts.token_name("tiktok", a.account), r["access_token"], r["refresh_token"])
    print(f"\nSaved. iRun can now post to TikTok for @{a.account}.")
else:
    print("\nTIKTOK_REFRESH_TOKEN =", r["refresh_token"])
