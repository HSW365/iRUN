"""Supabase REST + Storage helpers (service-role key; server-side only)."""
import os
import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = os.environ.get("IRUN_BUCKET", "irun-media")


def enabled():
    return bool(URL and KEY)


def _h(extra=None):
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def select(table, query=""):
    r = requests.get(f"{URL}/rest/v1/{table}?{query}", headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json()


def insert(table, row, upsert_on=None):
    prefer = "return=representation"
    q = ""
    if upsert_on:
        prefer += ",resolution=merge-duplicates"
        q = f"?on_conflict={upsert_on}"
    r = requests.post(f"{URL}/rest/v1/{table}{q}", headers=_h({"Prefer": prefer}), json=row, timeout=30)
    r.raise_for_status()
    out = r.json()
    return out[0] if isinstance(out, list) and out else out


def update(table, match, fields):
    q = "&".join(f"{k}=eq.{v}" for k, v in match.items())
    r = requests.patch(f"{URL}/rest/v1/{table}?{q}", headers=_h({"Prefer": "return=minimal"}), json=fields, timeout=30)
    r.raise_for_status()


def get_token(name):
    rows = select("irun_tokens", f"name=eq.{name}&select=value,refresh_value")
    return rows[0] if rows else None


def set_token(name, value, refresh_value=None, expires_at=None):
    row = {"name": name, "value": value}
    if refresh_value is not None:
        row["refresh_value"] = refresh_value
    if expires_at is not None:
        row["expires_at"] = expires_at
    insert("irun_tokens", row, upsert_on="name")


def upload_public(local_path, object_name, content_type="video/mp4"):
    with open(local_path, "rb") as f:
        r = requests.post(
            f"{URL}/storage/v1/object/{BUCKET}/{object_name}",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": content_type, "x-upsert": "true"},
            data=f, timeout=300,
        )
    r.raise_for_status()
    return f"{URL}/storage/v1/object/public/{BUCKET}/{object_name}"
