"""One-time TikTok login for iRun. Run on your PC:
    set TIKTOK_CLIENT_KEY=...   set TIKTOK_CLIENT_SECRET=...
    python engine/tiktok_auth.py
Open the printed link, approve with @hsw365media, copy the code shown on the callback page, paste it here.
Put the printed refresh token in GitHub secret TIKTOK_REFRESH_TOKEN (iRun rotates it automatically afterwards).
"""
import os
import secrets
import urllib.parse
import requests

REDIRECT = os.environ.get("TIKTOK_REDIRECT_URI", "https://hsw365.github.io/irun/callback.html")
ck, cs = os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"]
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": ck, "scope": "user.info.basic,video.publish", "response_type": "code",
    "redirect_uri": REDIRECT, "state": secrets.token_urlsafe(12)})
print("\nOpen this link and approve:\n\n" + url + "\n")
code = urllib.parse.unquote(input("Paste the code: ").strip())
r = requests.post("https://open.tiktokapis.com/v2/oauth/token/",
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  data={"client_key": ck, "client_secret": cs, "code": code,
                        "grant_type": "authorization_code", "redirect_uri": REDIRECT}, timeout=30).json()
if "refresh_token" not in r:
    raise SystemExit(f"Failed: {r}")
print("\nTIKTOK_REFRESH_TOKEN =", r["refresh_token"])
print("open_id =", r.get("open_id"), " scopes =", r.get("scope"))
