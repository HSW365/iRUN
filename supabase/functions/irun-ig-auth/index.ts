// iRun Instagram Business Login + Instagram workspace API (instagram.html).
//
// Login (Instagram API with Instagram Login):
//   GET  ?a=login[&account=<iRun account id>&o=<owner key>][&c=<company id>&k=<client key>]
//        -> 302 to instagram.com/oauth/authorize. Redirect URI is callback.html, state is "ig.<signed>".
//   POST {a:"exchange", code, state}   -> short-lived token -> long-lived token (60 days), stored server side.
//        Returns {u, s, username}: the browser keeps the session key, never the Instagram token.
//        If the login was started for an iRun account, the token is also stored in irun_tokens so the engine posts with it.
//
// Workspace actions, POST {a, u, s, ...}:
//   me                 profile + recent media                         (instagram_business_basic)
//   upload_url         {name, type} -> signed upload URL + public URL (media to publish)
//   create             {kind:"IMAGE"|"REELS", url, caption} -> container id   (instagram_business_content_publish)
//   status             {id} -> container status_code
//   publish            {id} -> published media id + permalink
//   comments           comments on recent posts                       (instagram_business_manage_comments)
//   reply_comment      {id, text}
//   hide_comment       {id, hide:boolean}
//   delete_comment     {id}
//   conversations      DMs sent to the account                        (instagram_business_manage_messages)
//   send               {to, text} -> reply, only inside a conversation the customer started and within 24 hours
//   disconnect         deletes the stored token and data for this account
//
// Meta callbacks (Business login settings):
//   POST ?a=deauthorize   signed_request -> token and data deleted
//   POST ?a=delete        signed_request -> data deleted, returns {url, confirmation_code}
//   GET  ?a=deletion&code=..  -> deletion status (shown on data-deletion.html)
//
// Secrets: IG_APP_ID, IG_APP_SECRET (Meta app > Instagram > API setup with Instagram login > Business login settings).
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const APP_ID = Deno.env.get("IG_APP_ID") ?? "";
const APP_SECRET = Deno.env.get("IG_APP_SECRET") ?? "";
const SITE = "https://hsw365.github.io/iRUN/";
const REDIRECT = SITE + "callback.html";
const GRAPH = "https://graph.instagram.com/v23.0";
const BUCKET = "irun-media";
const MAIN = "hsw365media";
const SCOPES = [
  "instagram_business_basic",
  "instagram_business_content_publish",
  "instagram_business_manage_messages",
  "instagram_business_manage_comments",
].join(",");

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
const page = (msg: string, s = 400) =>
  new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>iRun</title>` +
    `<body style="margin:0;background:#0a0a0f;color:#f4f4f7;font:16px system-ui;display:grid;place-items:center;min-height:100vh;padding:20px">` +
    `<div style="max-width:520px"><h1 style="font:900 40px Impact,sans-serif;margin:0 0 10px">iRUN</h1><p>${msg}</p>` +
    `<p><a style="color:#ef4444" href="${SITE}instagram.html">Back to iRun</a></p></div>`, { status: s, headers: { "Content-Type": "text/html; charset=utf-8" } });

// ---------- signing ----------
const enc = new TextEncoder();
const b64u = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64u = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
async function hmac(data: string) {
  const k = await crypto.subtle.importKey("raw", enc.encode(APP_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(data)));
}
const same = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((x, i) => x === b[i]);
async function signState(o: Record<string, unknown>) {
  const body = b64u(enc.encode(JSON.stringify(o)));
  return `ig.${body}.${b64u(await hmac(body))}`;
}
async function readState(s: string) {
  const [p, body, sig] = String(s ?? "").split(".");
  if (p !== "ig" || !body || !sig || !same(fromB64u(sig), await hmac(body))) return null;
  const o = JSON.parse(new TextDecoder().decode(fromB64u(body)));
  return o.exp > Date.now() ? o : null;
}
// Meta signed_request: "<sig>.<payload>", HMAC-SHA256 of the payload with the app secret.
async function signedRequest(sr: string) {
  const [sig, body] = String(sr ?? "").split(".");
  if (!sig || !body || !same(fromB64u(sig), await hmac(body))) return null;
  return JSON.parse(new TextDecoder().decode(fromB64u(body)));
}

// ---------- helpers ----------
async function setting(key: string) {
  const { data } = await db.from("irun_settings").select("value").eq("key", key).maybeSingle();
  return data?.value ?? null;
}
const tokenName = (account: string) => (account === MAIN ? "instagram" : `instagram:${account}`);
async function ig(path: string, opts: { method?: string; token: string; params?: Record<string, string>; body?: unknown }) {
  const u = new URL(path.startsWith("http") ? path : GRAPH + path);
  for (const [k, v] of Object.entries(opts.params ?? {})) u.searchParams.set(k, v);
  // Form-encoded body (what the Graph API documents); nested objects are sent as JSON strings.
  const form = opts.body
    ? new URLSearchParams(Object.entries(opts.body as Record<string, unknown>).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)]))
    : undefined;
  const r = await fetch(u, { method: opts.method ?? "GET", headers: { Authorization: `Bearer ${opts.token}` }, body: form });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.error) throw new Error(j?.error?.message ?? `Instagram request failed (${r.status})`);
  return j;
}
async function wipe(uid: string) {
  const { data } = await db.from("irun_ig_connections").select("account_id").eq("ig_user_id", uid).maybeSingle();
  if (data?.account_id) await db.from("irun_tokens").delete().eq("name", tokenName(data.account_id));
  await db.from("irun_ig_connections").delete().eq("ig_user_id", uid);
}
// Long-lived tokens last 60 days; refresh when older than a day and close to expiry.
async function fresh(c: any) {
  const left = c.expires_at ? new Date(c.expires_at).getTime() - Date.now() : 0;
  if (left > 7 * 86400_000) return c.token;
  try {
    const r = await ig("https://graph.instagram.com/refresh_access_token", { token: c.token, params: { grant_type: "ig_refresh_token" } });
    const exp = new Date(Date.now() + (r.expires_in ?? 5184000) * 1000).toISOString();
    await db.from("irun_ig_connections").update({ token: r.access_token, expires_at: exp, updated_at: new Date().toISOString() }).eq("ig_user_id", c.ig_user_id);
    if (c.account_id) await db.from("irun_tokens").upsert({ name: tokenName(c.account_id), value: r.access_token, expires_at: exp });
    return r.access_token;
  } catch {
    return c.token;
  }
}

// ---------- login ----------
async function login(url: URL) {
  if (!APP_ID || !APP_SECRET) return page("Instagram login is not configured yet (IG_APP_ID / IG_APP_SECRET).", 503);
  const st: Record<string, unknown> = { n: crypto.randomUUID(), exp: Date.now() + 15 * 60_000 };
  const account = url.searchParams.get("account");
  const c = url.searchParams.get("c");
  if (account) {
    const o = url.searchParams.get("o");
    if (!o || o !== (await setting("owner_key"))) return page("That owner link is not valid.", 401);
    st.acct = account;
  } else if (c) {
    const { data } = await db.from("irun_companies").select("id,client_key").eq("id", c).maybeSingle();
    if (!data || data.client_key !== url.searchParams.get("k")) return page("That company link is not valid.", 401);
    st.acct = data.id;
  }
  const a = new URL("https://www.instagram.com/oauth/authorize");
  a.searchParams.set("enable_fb_login", "0");
  a.searchParams.set("force_authentication", "1");
  a.searchParams.set("client_id", APP_ID);
  a.searchParams.set("redirect_uri", REDIRECT);
  a.searchParams.set("response_type", "code");
  a.searchParams.set("scope", SCOPES);
  a.searchParams.set("state", await signState(st));
  return Response.redirect(a.toString(), 302);
}

async function exchange(b: any) {
  if (!APP_ID || !APP_SECRET) return json({ error: "Instagram login is not configured yet." }, 503);
  const st = await readState(b.state);
  if (!st) return json({ error: "This login link expired. Start again." }, 400);
  const code = String(b.code ?? "").replace(/#_$/, "");
  if (!code) return json({ error: "No code received from Instagram." }, 400);

  const form = new URLSearchParams({ client_id: APP_ID, client_secret: APP_SECRET, grant_type: "authorization_code", redirect_uri: REDIRECT, code });
  const r = await fetch("https://api.instagram.com/oauth/access_token", { method: "POST", body: form });
  const short = await r.json().catch(() => ({}));
  if (!r.ok || !short.access_token) return json({ error: short?.error_message ?? short?.error?.message ?? "Instagram did not accept the login." }, 400);
  const scopes = Array.isArray(short.permissions) ? short.permissions.join(",") : String(short.permissions ?? "");

  const lr = await fetch(`https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=${encodeURIComponent(APP_SECRET)}&access_token=${encodeURIComponent(short.access_token)}`);
  const long = await lr.json().catch(() => ({}));
  if (!lr.ok || !long.access_token) return json({ error: long?.error?.message ?? "Could not get a long-lived token." }, 400);
  const token = long.access_token;
  const expires = new Date(Date.now() + (long.expires_in ?? 5184000) * 1000).toISOString();

  const me = await ig("/me", { token, params: { fields: "user_id,username,name,profile_picture_url,account_type" } });
  const uid = String(me.user_id ?? short.user_id);
  const session = b64u(crypto.getRandomValues(new Uint8Array(24)));
  const { data: prev } = await db.from("irun_ig_connections").select("account_id").eq("ig_user_id", uid).maybeSingle();
  const account = (st.acct as string) ?? prev?.account_id ?? null;
  const { error } = await db.from("irun_ig_connections").upsert({
    ig_user_id: uid, username: me.username, name: me.name ?? null, picture: me.profile_picture_url ?? null,
    account_type: me.account_type ?? null, token, expires_at: expires, session_key: session, account_id: account,
    scopes, updated_at: new Date().toISOString(),
  });
  if (error) return json({ error: error.message }, 500);
  if (account) {
    await db.from("irun_tokens").upsert({ name: tokenName(account), value: token, expires_at: expires });
    if (account !== MAIN) await db.from("irun_activity").insert({ company_id: account, agent: "instagram", action: `Instagram @${me.username} connected` }).then(() => {}, () => {});
  }
  return json({ u: uid, s: session, username: me.username, account });
}

// ---------- workspace ----------
const within24h = (t: string) => Date.now() - new Date(t).getTime() < 24 * 3600_000;

async function action(b: any) {
  const { data: c } = await db.from("irun_ig_connections").select("*").eq("ig_user_id", String(b.u ?? "")).maybeSingle();
  if (!c || !b.s || c.session_key !== b.s) return json({ error: "Connect Instagram again." }, 401);
  const token = await fresh(c);

  switch (b.a) {
    case "me": {
      const [p, m] = await Promise.all([
        ig("/me", { token, params: { fields: "user_id,username,name,profile_picture_url,account_type,followers_count,follows_count,media_count" } }),
        ig("/me/media", { token, params: { fields: "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,comments_count,like_count", limit: "18" } }),
      ]);
      await db.from("irun_ig_connections").update({ username: p.username, name: p.name ?? null, picture: p.profile_picture_url ?? null }).eq("ig_user_id", c.ig_user_id);
      return json({ profile: p, media: m.data ?? [], account: c.account_id, expires_at: c.expires_at });
    }
    case "upload_url": {
      const type = String(b.type ?? "");
      if (!/^(image\/jpeg|video\/mp4|video\/quicktime)$/.test(type)) return json({ error: "Use a JPG image or an MP4/MOV video." }, 400);
      const ext = type === "image/jpeg" ? "jpg" : type === "video/mp4" ? "mp4" : "mov";
      const path = `ig-uploads/${c.ig_user_id}/${Date.now()}-${crypto.randomUUID().slice(0, 8)}.${ext}`;
      const { data, error } = await db.storage.from(BUCKET).createSignedUploadUrl(path);
      if (error) return json({ error: error.message }, 500);
      const pub = db.storage.from(BUCKET).getPublicUrl(path).data.publicUrl;
      return json({ upload: data.signedUrl, url: pub });
    }
    case "create": {
      const url = String(b.url ?? "");
      if (!/^https:\/\//.test(url)) return json({ error: "Media must be at a public https URL." }, 400);
      const kind = b.kind === "REELS" ? "REELS" : "IMAGE";
      const body: Record<string, string> = { caption: String(b.caption ?? "").slice(0, 2200) };
      if (kind === "REELS") Object.assign(body, { media_type: "REELS", video_url: url, share_to_feed: "true" });
      else body.image_url = url;
      const r = await ig(`/${c.ig_user_id}/media`, { method: "POST", token, body });
      return json({ id: r.id });
    }
    case "status": {
      const r = await ig(`/${encodeURIComponent(String(b.id))}`, { token, params: { fields: "status_code,status" } });
      return json({ status: r.status_code, detail: r.status ?? null });
    }
    case "publish": {
      const r = await ig(`/${c.ig_user_id}/media_publish`, { method: "POST", token, body: { creation_id: String(b.id) } });
      const m = await ig(`/${r.id}`, { token, params: { fields: "id,permalink" } }).catch(() => ({ id: r.id }));
      return json({ id: r.id, permalink: m.permalink ?? null });
    }
    case "comments": {
      const m = await ig("/me/media", { token, params: { fields: "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,comments_count", limit: "12" } });
      const posts = (m.data ?? []).filter((p: any) => p.comments_count > 0).slice(0, 8);
      const out = await Promise.all(posts.map(async (p: any) => {
        const cm = await ig(`/${p.id}/comments`, { token, params: { fields: "id,text,username,timestamp,hidden,replies{id,text,username,timestamp}", limit: "25" } })
          .catch(() => ({ data: [] }));
        return { post: p, comments: cm.data ?? [] };
      }));
      return json({ posts: out });
    }
    case "reply_comment": {
      const text = String(b.text ?? "").trim().slice(0, 1000);
      if (!text) return json({ error: "Write a reply first." }, 400);
      const r = await ig(`/${encodeURIComponent(String(b.id))}/replies`, { method: "POST", token, body: { message: text } });
      return json({ id: r.id });
    }
    case "hide_comment": {
      await ig(`/${encodeURIComponent(String(b.id))}`, { method: "POST", token, body: { hide: !!b.hide } });
      return json({ ok: true });
    }
    case "delete_comment": {
      await ig(`/${encodeURIComponent(String(b.id))}`, { method: "DELETE", token });
      return json({ ok: true });
    }
    case "conversations": {
      const r = await ig("/me/conversations", {
        token, params: { platform: "instagram", fields: "id,updated_time,participants,messages.limit(20){id,from,to,message,created_time}", limit: "20" },
      });
      const convos = (r.data ?? []).map((cv: any) => {
        const other = (cv.participants?.data ?? []).find((p: any) => String(p.id) !== String(c.ig_user_id)) ?? null;
        const msgs = (cv.messages?.data ?? []).slice().reverse();
        const lastIn = [...msgs].reverse().find((x: any) => String(x.from?.id) !== String(c.ig_user_id));
        return { id: cv.id, updated: cv.updated_time, with: other, messages: msgs, can_reply: !!lastIn && within24h(lastIn.created_time) };
      });
      return json({ me: c.ig_user_id, conversations: convos });
    }
    case "send": {
      const to = String(b.to ?? "");
      const text = String(b.text ?? "").trim().slice(0, 1000);
      if (!to || !text) return json({ error: "Write a message first." }, 400);
      // Replies only: the customer must have messaged this account in the last 24 hours.
      const r = await ig("/me/conversations", { token, params: { platform: "instagram", user_id: to, fields: "messages.limit(10){from,created_time}" } });
      const msgs = r.data?.[0]?.messages?.data ?? [];
      const lastIn = msgs.find((x: any) => String(x.from?.id) === to);
      if (!lastIn || !within24h(lastIn.created_time)) return json({ error: "iRun only replies to people who messaged you in the last 24 hours." }, 403);
      const s = await ig("/me/messages", { method: "POST", token, body: { recipient: { id: to }, message: { text } } });
      return json({ id: s.message_id ?? null });
    }
    case "disconnect": {
      await wipe(c.ig_user_id);
      return json({ ok: true });
    }
  }
  return json({ error: "Unknown action." }, 400);
}

// ---------- Meta callbacks ----------
async function metaCallback(req: Request, kind: "deauthorize" | "delete") {
  const form = await req.formData().catch(() => null);
  const data = await signedRequest(String(form?.get("signed_request") ?? ""));
  if (!data?.user_id) return json({ error: "Invalid signed_request" }, 400);
  const uid = String(data.user_id);
  await wipe(uid);
  if (kind === "deauthorize") return json({ ok: true });
  const code = b64u(crypto.getRandomValues(new Uint8Array(9)));
  await db.from("irun_ig_deletions").insert({ code, ig_user_id: uid, status: "completed" });
  return json({ url: `${SITE}data-deletion.html?code=${code}`, confirmation_code: code });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const url = new URL(req.url);
  const a = url.searchParams.get("a");
  try {
    if (req.method === "GET" && a === "login") return await login(url);
    if (req.method === "GET" && a === "deletion") {
      const { data } = await db.from("irun_ig_deletions").select("code,status,created_at").eq("code", url.searchParams.get("code") ?? "").maybeSingle();
      return data ? json(data) : json({ error: "No deletion request with that code." }, 404);
    }
    if (req.method === "GET" && a === "config") return json({ ready: !!(APP_ID && APP_SECRET) });
    if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
    if (a === "deauthorize") return await metaCallback(req, "deauthorize");
    if (a === "delete") return await metaCallback(req, "delete");
    const b = await req.json().catch(() => ({}));
    if (b.a === "exchange") return await exchange(b);
    return await action(b);
  } catch (e) {
    return json({ error: String(e instanceof Error ? e.message : e) }, 500);
  }
});
