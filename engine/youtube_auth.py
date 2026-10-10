"""One-time YouTube login for an iRun account. Run on your PC:
    set YOUTUBE_CLIENT_ID=...   set YOUTUBE_CLIENT_SECRET=...
    (optional, to save the login straight into iRun)  set SUPABASE_URL=...  set SUPABASE_SERVICE_KEY=...
    python engine/youtube_auth.py --account hoodstar365
It opens Google in your browser. Pick the channel, approve, and the login is caught automatically.
With the Supabase variables set, the login is saved for that account. Without them, the refresh token is
printed: for hoodstar365 put it in GitHub secret YOUTUBE_REFRESH_TOKEN.
"""
import argparse
import http.server
import os
import secrets
import sys
import urllib.parse
import webbrowser

import requests

sys.path.insert(0, os.path.dirname(__file__))
import accounts  # noqa: E402
import db  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--account", default=accounts.YT_MAIN, help="account id from config/accounts.json")
ap.add_argument("--port", type=int, default=8765)
a = ap.parse_args()
accounts.get(a.account)  # fail early on a typo

cid, cs = os.environ["YOUTUBE_CLIENT_ID"], os.environ["YOUTUBE_CLIENT_SECRET"]
redirect = f"http://127.0.0.1:{a.port}"
state = secrets.token_urlsafe(12)
url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": cid, "redirect_uri": redirect, "response_type": "code", "access_type": "offline",
    "prompt": "consent", "scope": "https://www.googleapis.com/auth/youtube.upload", "state": state})
got = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if q.get("state", [""])[0] == state and "code" in q:
            got["code"] = q["code"][0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>iRun: YouTube connected. You can close this tab.</h2>" if got else b"<h2>No code received.</h2>")

    def log_message(self, *_):
        pass


print(f"\nLog in with the Google account that owns @{a.account}'s channel and approve:\n\n{url}\n")
webbrowser.open(url)
srv = http.server.HTTPServer(("127.0.0.1", a.port), Handler)
while not got:
    srv.handle_request()
r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
    "client_id": cid, "client_secret": cs, "code": got["code"], "grant_type": "authorization_code",
    "redirect_uri": redirect}).json()
if "refresh_token" not in r:
    raise SystemExit(f"Failed: {r}")
if db.enabled():
    db.set_token(accounts.token_name("youtube", a.account), r["access_token"], r["refresh_token"])
    print(f"\nSaved. iRun can now post YouTube Shorts for @{a.account}.")
else:
    print("\nYOUTUBE_REFRESH_TOKEN =", r["refresh_token"])
