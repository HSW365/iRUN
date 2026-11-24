// iRun Connect: the integrations hub behind connect.html.
//
// Every call is POST {owner, a, ...}. owner must match irun_settings.owner_key (same check as irun-ai).
//   catalog                                  -> each integration: connected, label, toggles, last error. Never secrets.
//   save         {id, creds}                 -> checks the credentials with the service, then stores them server side
//   settings     {id, auto_share?, lead_alerts?, meta?}
//   disconnect   {id}
//   oauth_start  {id, creds:{client_id, client_secret}}  -> {url}       (canva, gdrive)
//   oauth_finish {code, state}               -> exchanges the code, stores the tokens
//   run          {id, op, args}              -> one action on one service (see OPS below)
//   library      {limit?}                    -> media brought into iRun (Canva, Figma, Spotify, Shopify, uploads)
//   library_add  {url, kind, title?, source?}
//   library_del  {lib}
//   upload_url   {name, type}                -> signed upload URL in the irun-connect bucket + its public URL
//   share        {text, url?, kind?, link?, to?: string[]}  -> Discord / Telegram / Slack
//   ig_publish   {url, kind, caption, lib?}   -> posts to Instagram @hoodstar365 (container -> publish)
//   ig_finish    {container, caption, url, kind, lib?}       -> finishes a video post that was still processing
//
// Credentials live in irun_integrations (RLS on, no policies). The browser only ever gets labels and masked hints.
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const SITE = "https://hsw365.github.io/iRUN/";
const REDIRECT = SITE + "connect.html";
const BUCKET = "irun-connect";
const IG_ACCOUNT = "hoodstar365";
const IG_GRAPH = "https://graph.instagram.com/v23.0";
const UA = "HSW365-iRun-Connect/1.0 (hsw365media@gmail.com)";
const IRUN_REPO = "HSW365/iRUN";

const IDS = ["discord", "telegram", "slack", "canva", "figma", "shopify", "stripe", "hubspot", "calendly", "zoom",
  "leads", "instagram", "spotify", "github", "render", "gdrive", "domains"] as const;
const FREE = new Set(["leads", "domains"]); // no account needed
const SHARE = ["discord", "telegram", "slack"];

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
class Fail extends Error { constructor(msg: string, public status = 400) { super(msg); } }
const need = (v: unknown, what: string) => { if (v === undefined || v === null || String(v).trim() === "") throw new Fail(`Add ${what}.`); return String(v).trim(); };

// ---------------------------------------------------------------- helpers
const enc = new TextEncoder();
const b64u = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const rand = (n = 32) => b64u(crypto.getRandomValues(new Uint8Array(n)));
const sha256 = async (s: string) => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)));
const basic = (a: string, b: string) => "Basic " + btoa(`${a}:${b}`);
const mask = (s: unknown) => { const t = String(s ?? ""); return t.length > 8 ? `${t.slice(0, 4)}…${t.slice(-4)}` : t ? "set" : ""; };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowIso = () => new Date().toISOString();
const https = (u: unknown) => { const s = String(u ?? ""); if (!/^https:\/\//i.test(s)) throw new Fail("That link has to start with https://"); return s; };

async function http(url: string, opts: RequestInit & { timeout?: number; label?: string } = {}) {
  const { timeout = 25000, label = new URL(url).hostname, ...init } = opts;
  let r: Response;
  try {
    r = await fetch(url, { ...init, signal: AbortSignal.timeout(timeout), headers: { "User-Agent": UA, ...(init.headers ?? {}) } });
  } catch (e) {
    throw new Fail(`${label} did not answer (${e instanceof Error ? e.name : "network"}). Try again.`, 502);
  }
  const text = await r.text();
  let body: any = text;
  try { body = text ? JSON.parse(text) : {}; } catch { /* plain text */ }
  if (!r.ok) {
    const m = typeof body === "object" && body
      ? body.error_description || body.error?.message || body.message || body.description || body.err || (typeof body.error === "string" ? body.error : "") ||
        body.errors?.[0]?.message || body.errors?.[0]?.detail || body.detail
      : String(body).slice(0, 200);
    throw new Fail(`${label}: ${m || `HTTP ${r.status}`}`, r.status === 401 || r.status === 403 ? 400 : 502);
  }
  return body;
}

async function setting(key: string) {
  const { data } = await db.from("irun_settings").select("value").eq("key", key).maybeSingle();
  return data?.value ?? null;
}
async function getInt(id: string) {
  const { data } = await db.from("irun_integrations").select("*").eq("id", id).maybeSingle();
  return data as any;
}
async function putInt(id: string, patch: Record<string, unknown>) {
  const { error } = await db.from("irun_integrations").upsert({ id, ...patch, updated_at: nowIso() });
  if (error) throw new Fail(`Could not save: ${error.message}`, 500);
}
async function patchInt(id: string, patch: Record<string, unknown>) {
  await db.from("irun_integrations").update({ ...patch, updated_at: nowIso() }).eq("id", id);
}
async function creds(id: string) {
  const row = await getInt(id);
  if (!row || row.status === "pending") throw new Fail(`Connect ${id} first.`);
  return row;
}
async function igToken() {
  const { data } = await db.from("irun_tokens").select("value").eq("name", `instagram:${IG_ACCOUNT}`).maybeSingle();
  if (!data?.value) throw new Fail("Instagram @hoodstar365 is not connected. Connect it from the Instagram card.");
  return data.value as string;
}

// Download a file and store it in the irun-connect bucket so it never expires (Canva and Figma links last hours).
async function keep(url: string, folder: string, name: string) {
  const r = await fetch(url, { signal: AbortSignal.timeout(60000), headers: { "User-Agent": UA } });
  if (!r.ok) throw new Fail(`Could not download the file (${r.status}).`, 502);
  let type = (r.headers.get("content-type") || "").split(";")[0].trim();
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (bytes.length > 100 * 1024 * 1024) throw new Fail("That file is over 100 MB.");
  if (!/^(image\/(jpeg|png|webp)|video\/mp4)$/.test(type)) {
    // CDNs sometimes send octet-stream; sniff the magic bytes.
    if (bytes[0] === 0xff && bytes[1] === 0xd8) type = "image/jpeg";
    else if (bytes[0] === 0x89 && bytes[1] === 0x50) type = "image/png";
    else if (bytes[8] === 0x57 && bytes[9] === 0x45) type = "image/webp";
    else if (bytes[4] === 0x66 && bytes[5] === 0x74 && bytes[6] === 0x79 && bytes[7] === 0x70) type = "video/mp4";
    else throw new Fail(`iRun keeps JPEG, PNG, WebP and MP4 files. This one is ${type || "unknown"}.`);
  }
  const ext = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "video/mp4": "mp4" }[type]!;
  const safe = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "file";
  const path = `${folder}/${Date.now().toString(36)}-${safe}.${ext}`;
  const { error } = await db.storage.from(BUCKET).upload(path, bytes, { contentType: type, upsert: true });
  if (error) throw new Fail(`Storage: ${error.message}`, 500);
  return { url: db.storage.from(BUCKET).getPublicUrl(path).data.publicUrl, type, kind: type.startsWith("video") ? "video" : "image", size: bytes.length };
}
async function addLib(row: { source: string; kind: string; title?: string; url: string; ref?: string; meta?: unknown }) {
  const { data, error } = await db.from("irun_library").insert({ ...row, meta: row.meta ?? {} }).select("*").single();
  if (error) throw new Fail(`Library: ${error.message}`, 500);
  return data;
}
async function markPosted(lib: unknown, entry: Record<string, unknown>) {
  if (!lib) return;
  const { data } = await db.from("irun_library").select("posted").eq("id", lib).maybeSingle();
  if (!data) return;
  await db.from("irun_library").update({ posted: [...(data.posted ?? []), { ...entry, at: nowIso() }] }).eq("id", lib);
}

// ---------------------------------------------------------------- sharing (Discord / Telegram / Slack)
type Msg = { text: string; url?: string; kind?: string; link?: string };
const SENDERS: Record<string, (c: any, m: Msg) => Promise<unknown>> = {
  async discord(c, m) {
    const content = [m.text, m.link, m.url && m.url !== m.link ? m.url : ""].filter(Boolean).join("\n").slice(0, 2000);
    const r = await http(`${c.webhook}?wait=true`, { method: "POST", label: "Discord", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, username: "iRun" }) });
    return { id: r?.id };
  },
  async telegram(c, m) {
    const api = `https://api.telegram.org/bot${c.token}`;
    const cap = [m.text, m.link].filter(Boolean).join("\n\n");
    const post = (method: string, body: Record<string, unknown>) =>
      http(`${api}/${method}`, { method: "POST", label: "Telegram", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_id: c.chat, ...body }) });
    if (m.url && (m.kind === "video" || m.kind === "image")) {
      try {
        const r = await post(m.kind === "video" ? "sendVideo" : "sendPhoto", { [m.kind === "video" ? "video" : "photo"]: m.url, caption: cap.slice(0, 1024) });
        return { id: r?.result?.message_id };
      } catch { /* too big for a URL upload: send the link instead */ }
    }
    const r = await post("sendMessage", { text: [cap, m.url && m.url !== m.link ? m.url : ""].filter(Boolean).join("\n\n").slice(0, 4096) });
    return { id: r?.result?.message_id };
  },
  async slack(c, m) {
    const text = [m.text, m.link, m.url && m.url !== m.link ? m.url : ""].filter(Boolean).join("\n").slice(0, 3800);
    await http(c.webhook, { method: "POST", label: "Slack", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    return { ok: true };
  },
};
async function share(m: Msg, to?: string[], onlyAuto = false) {
  const { data } = await db.from("irun_integrations").select("*").in("id", SHARE);
  const rows = (data ?? []).filter((r: any) => r.status === "connected" && (to?.length ? to.includes(r.id) : onlyAuto ? r.auto_share : true));
  const out: Record<string, unknown> = {};
  for (const r of rows) {
    try { out[r.id] = await SENDERS[r.id](r.creds, m); await patchInt(r.id, { last_error: null }); }
    catch (e) { out[r.id] = { error: e instanceof Error ? e.message : String(e) }; await patchInt(r.id, { last_error: String((out[r.id] as any).error).slice(0, 300) }); }
  }
  return out;
}

// ---------------------------------------------------------------- Instagram (@hoodstar365)
async function igCall(path: string, token: string, params: Record<string, string> = {}, method = "GET") {
  const u = new URL(path.startsWith("http") ? path : IG_GRAPH + path);
  const body = method === "POST" ? new URLSearchParams(params) : undefined;
  if (method === "GET") for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  return http(u.toString(), { method, label: "Instagram", headers: { Authorization: `Bearer ${token}` }, body });
}
async function igPublish(args: any) {
  const token = await igToken();
  const kind = args.kind === "video" ? "video" : "image";
  const url = https(args.url);
  const caption = String(args.caption ?? "").slice(0, 2200);
  if (kind === "image") {
    const head = await fetch(url, { method: "HEAD", signal: AbortSignal.timeout(15000) }).catch(() => null);
    const ct = head?.headers.get("content-type") ?? "";
    if (ct && !/jpe?g/i.test(ct)) throw new Fail("Instagram only takes JPEG images. Convert it first.", 415);
  }
  const me = await igCall("/me", token, { fields: "user_id,username" });
  const uid = String(me.user_id ?? me.id);
  const c = await igCall(`/${uid}/media`, token, kind === "video"
    ? { media_type: "REELS", video_url: url, caption, share_to_feed: "true" }
    : { image_url: url, caption }, "POST");
  return igFinish({ ...args, container: c.id, kind, url, caption, uid, token });
}
async function igFinish(args: any) {
  const token = args.token ?? await igToken();
  const uid = args.uid ?? String((await igCall("/me", token, { fields: "user_id" })).user_id);
  const started = Date.now();
  for (;;) {
    const st = await igCall(`/${args.container}`, token, { fields: "status_code,status" });
    if (st.status_code === "FINISHED") break;
    if (st.status_code === "ERROR" || st.status_code === "EXPIRED") throw new Fail(`Instagram could not process it: ${st.status ?? st.status_code}`, 502);
    if (Date.now() - started > 90000) return { pending: true, container: args.container };
    await sleep(5000);
  }
  const p = await igCall(`/${uid}/media_publish`, token, { creation_id: String(args.container) }, "POST");
  let permalink = "";
  try { permalink = (await igCall(`/${p.id}`, token, { fields: "permalink" })).permalink ?? ""; } catch { /* optional */ }
  await markPosted(args.lib, { to: "instagram", id: p.id, permalink });
  await db.from("irun_posts").insert({
    platform: "instagram", account: IG_ACCOUNT, product_id: "connect", status: "posted", mode: "live",
    caption: args.caption, video_url: args.url, external_id: p.id, posted_at: nowIso(),
    media: { kind: args.kind, url: args.url, source: "connect" }, result: { post_id: p.id, permalink },
  });
  const shared = await share({ text: args.caption, url: args.url, kind: args.kind, link: permalink }, undefined, true);
  return { posted: true, id: p.id, permalink, shared };
}

// ---------------------------------------------------------------- OAuth (Canva, Google Drive)
const OAUTH: Record<string, { auth: string; token: string; scope: string; pkce: boolean; extra?: Record<string, string> }> = {
  canva: {
    auth: "https://www.canva.com/api/oauth/authorize",
    token: "https://api.canva.com/rest/v1/oauth/token",
    scope: "profile:read design:meta:read design:content:read design:content:write asset:read asset:write",
    pkce: true,
  },
  gdrive: {
    auth: "https://accounts.google.com/o/oauth2/v2/auth",
    token: "https://oauth2.googleapis.com/token",
    scope: "openid email https://www.googleapis.com/auth/drive.file",
    pkce: true,
    extra: { access_type: "offline", prompt: "consent", include_granted_scopes: "true" },
  },
};
async function tokenCall(id: string, c: any, form: Record<string, string>) {
  const o = OAUTH[id];
  const headers: Record<string, string> = { "Content-Type": "application/x-www-form-urlencoded" };
  if (id === "canva") headers.Authorization = basic(c.client_id, c.client_secret);
  else Object.assign(form, { client_id: c.client_id, client_secret: c.client_secret });
  return http(o.token, { method: "POST", label: id === "canva" ? "Canva" : "Google", headers, body: new URLSearchParams(form) });
}
async function oauthStart(id: string, input: any) {
  const o = OAUTH[id];
  if (!o) throw new Fail("That service doesn't use a sign-in.");
  const prev = await getInt(id);
  const client_id = String(input?.client_id ?? "").trim() || prev?.creds?.client_id;
  const client_secret = String(input?.client_secret ?? "").trim() || prev?.creds?.client_secret;
  need(client_id, "the client ID"); need(client_secret, "the client secret");
  const state = `${id}.${rand(18)}`;
  const verifier = rand(48);
  const u = new URL(o.auth);
  const q: Record<string, string> = { response_type: "code", client_id, redirect_uri: REDIRECT, scope: o.scope, state, ...(o.extra ?? {}) };
  if (o.pkce) Object.assign(q, { code_challenge: b64u(await sha256(verifier)), code_challenge_method: id === "canva" ? "s256" : "S256" });
  for (const [k, v] of Object.entries(q)) u.searchParams.set(k, v);
  const keepCreds = prev && prev.status !== "pending" ? prev.creds : {};
  await putInt(id, {
    creds: { ...keepCreds, client_id, client_secret },
    meta: { ...(prev?.meta ?? {}), oauth: { state, verifier, at: Date.now() } },
    status: prev && prev.status === "connected" ? "connected" : "pending",
  });
  return { url: u.toString(), redirect: REDIRECT };
}
async function oauthFinish(code: string, state: string) {
  const id = String(state).split(".")[0];
  const row = await getInt(id);
  const o = row?.meta?.oauth;
  if (!OAUTH[id] || !o || o.state !== state || Date.now() - o.at > 20 * 60000) throw new Fail("That sign-in link expired. Start the connection again.");
  const t = await tokenCall(id, row.creds, { grant_type: "authorization_code", code, redirect_uri: REDIRECT, code_verifier: o.verifier });
  const c = { ...row.creds, access_token: t.access_token, refresh_token: t.refresh_token ?? row.creds.refresh_token, expires_at: Date.now() + (t.expires_in ?? 3600) * 1000 };
  let label = id === "canva" ? "Canva" : "Google Drive";
  try {
    if (id === "canva") label = (await http("https://api.canva.com/rest/v1/users/me/profile", { label: "Canva", headers: { Authorization: `Bearer ${c.access_token}` } })).profile?.display_name || label;
    else label = (await http("https://www.googleapis.com/oauth2/v3/userinfo", { label: "Google", headers: { Authorization: `Bearer ${c.access_token}` } })).email || label;
  } catch { /* label is cosmetic */ }
  const meta = { ...row.meta, label };
  delete (meta as any).oauth;
  await putInt(id, { creds: c, meta, status: "connected", last_error: null, connected_at: row.status === "connected" ? row.connected_at : nowIso() });
  return { id, label };
}
async function bearer(id: string) {
  const row = await creds(id);
  const c = row.creds;
  if (c.access_token && c.expires_at && c.expires_at - Date.now() > 120000) return c.access_token as string;
  if (!c.refresh_token) throw new Fail(`Sign in to ${id} again.`);
  const t = await tokenCall(id, c, { grant_type: "refresh_token", refresh_token: c.refresh_token });
  const next = { ...c, access_token: t.access_token, refresh_token: t.refresh_token ?? c.refresh_token, expires_at: Date.now() + (t.expires_in ?? 3600) * 1000 };
  await patchInt(id, { creds: next });
  return next.access_token as string;
}

// ---------------------------------------------------------------- credential checks (save)
const VERIFY: Record<string, (c: any) => Promise<{ creds: any; label: string; meta?: any }>> = {
  async discord(c) {
    const webhook = need(c.webhook, "the Discord webhook URL");
    if (!/^https:\/\/(canary\.|ptb\.)?(discord|discordapp)\.com\/api\/webhooks\/\d+\/[\w-]+$/.test(webhook)) throw new Fail("That isn't a Discord webhook URL. It starts with https://discord.com/api/webhooks/");
    const r = await http(webhook, { label: "Discord" });
    return { creds: { webhook }, label: r.name ? `${r.name}` : "Discord channel", meta: { channel_id: r.channel_id, guild_id: r.guild_id } };
  },
  async telegram(c) {
    const token = need(c.token, "the bot token"), chat = need(c.chat, "the channel or chat");
    const me = await http(`https://api.telegram.org/bot${token}/getMe`, { label: "Telegram" });
    const ch = await http(`https://api.telegram.org/bot${token}/getChat?chat_id=${encodeURIComponent(chat)}`, { label: "Telegram" });
    const r = ch.result ?? {};
    return { creds: { token, chat }, label: r.username ? `@${r.username}` : r.title || chat, meta: { bot: me.result?.username } };
  },
  async slack(c) {
    const webhook = need(c.webhook, "the Slack webhook URL");
    if (!/^https:\/\/hooks\.slack\.com\/(services|workflows|triggers)\/[\w/-]+$/.test(webhook)) throw new Fail("That isn't a Slack incoming webhook URL. It starts with https://hooks.slack.com/");
    return { creds: { webhook }, label: String(c.label || "Slack channel").slice(0, 60) };
  },
  async figma(c) {
    const token = need(c.token, "the Figma access token");
    const r = await http("https://api.figma.com/v1/me", { label: "Figma", headers: { "X-Figma-Token": token } });
    return { creds: { token }, label: r.handle || r.email || "Figma" };
  },
  async shopify(c) {
    const store = need(c.store, "your store domain").replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
    await http(`https://${store}/products.json?limit=1`, { label: "Shopify" });
    const out: any = { store };
    let label = store;
    if (String(c.token ?? "").trim()) {
      const admin = need(c.admin, "the .myshopify.com address (needed with an Admin API token)").replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
      if (!admin.endsWith(".myshopify.com")) throw new Fail("The admin address ends in .myshopify.com");
      const r = await shopGql({ admin, token: c.token.trim() }, "{ shop { name } }");
      Object.assign(out, { admin, token: c.token.trim() });
      label = r.shop?.name || store;
    }
    return { creds: out, label };
  },
  async stripe(c) {
    const key = need(c.key, "the Stripe key");
    if (!/^(rk|sk)_(live|test)_/.test(key)) throw new Fail("Use a restricted key (rk_live_...) or secret key from Stripe > Developers > API keys.");
    await http("https://api.stripe.com/v1/balance", { label: "Stripe", headers: { Authorization: basic(key, "") } });
    let label = key.includes("_test_") ? "Stripe (test mode)" : "Stripe";
    try { const a = await http("https://api.stripe.com/v1/account", { label: "Stripe", headers: { Authorization: basic(key, "") } }); label = a.settings?.dashboard?.display_name || a.business_profile?.name || label; } catch { /* restricted keys may not read the account */ }
    return { creds: { key }, label };
  },
  async hubspot(c) {
    const token = need(c.token, "the HubSpot private app token");
    await http("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", { label: "HubSpot", headers: { Authorization: `Bearer ${token}` } });
    let label = "HubSpot";
    try { const a = await http("https://api.hubapi.com/account-info/v3/details", { label: "HubSpot", headers: { Authorization: `Bearer ${token}` } }); label = a.companyName || `HubSpot ${a.portalId}`; } catch { /* optional */ }
    return { creds: { token }, label };
  },
  async calendly(c) {
    const token = need(c.token, "the Calendly personal access token");
    const r = await http("https://api.calendly.com/users/me", { label: "Calendly", headers: { Authorization: `Bearer ${token}` } });
    return { creds: { token }, label: r.resource?.name || "Calendly", meta: { scheduling_url: r.resource?.scheduling_url, user: r.resource?.uri } };
  },
  async zoom(c) {
    const cc = { account_id: need(c.account_id, "the Account ID"), client_id: need(c.client_id, "the Client ID"), client_secret: need(c.client_secret, "the Client secret") };
    const t = await zoomToken(cc);
    const me = await http("https://api.zoom.us/v2/users/me", { label: "Zoom", headers: { Authorization: `Bearer ${t}` } });
    return { creds: cc, label: me.email || me.display_name || "Zoom" };
  },
  async spotify(c) {
    const cc = { client_id: need(c.client_id, "the Client ID"), client_secret: need(c.client_secret, "the Client secret") };
    await spotifyToken(cc);
    return { creds: cc, label: "Spotify", meta: { artist: String(c.artist || "HOODSTAR365").trim() } };
  },
  async github(c) {
    const token = String(c.token ?? "").trim();
    const owner = String(c.owner || "HSW365").trim();
    if (token) {
      const u = await http("https://api.github.com/user", { label: "GitHub", headers: gh(token) });
      return { creds: { token, owner }, label: `@${u.login}` };
    }
    const u = await http(`https://api.github.com/users/${encodeURIComponent(owner)}`, { label: "GitHub", headers: gh("") });
    return { creds: { owner }, label: `@${u.login} (public)` };
  },
  async render(c) {
    const key = need(c.key, "the Render API key");
    const r = await http("https://api.render.com/v1/owners?limit=5", { label: "Render", headers: { Authorization: `Bearer ${key}`, Accept: "application/json" } });
    return { creds: { key }, label: r?.[0]?.owner?.name || r?.[0]?.owner?.email || "Render" };
  },
};

// ---------------------------------------------------------------- service helpers
async function shopGql(c: { admin: string; token: string }, query: string, variables: unknown = {}) {
  const r = await http(`https://${c.admin}/admin/api/2025-07/graphql.json`, {
    method: "POST", label: "Shopify", headers: { "Content-Type": "application/json", "X-Shopify-Access-Token": c.token }, body: JSON.stringify({ query, variables }),
  });
  if (r.errors?.length) throw new Fail(`Shopify: ${r.errors[0].message}`, 502);
  return r.data;
}
async function zoomToken(c: any) {
  const r = await http(`https://zoom.us/oauth/token?grant_type=account_credentials&account_id=${encodeURIComponent(c.account_id)}`, {
    method: "POST", label: "Zoom", headers: { Authorization: basic(c.client_id, c.client_secret) },
  });
  return r.access_token as string;
}
async function spotifyToken(c: any) {
  const r = await http("https://accounts.spotify.com/api/token", {
    method: "POST", label: "Spotify", headers: { Authorization: basic(c.client_id, c.client_secret), "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "client_credentials" }),
  });
  return r.access_token as string;
}
const gh = (token: string) => ({ Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", ...(token ? { Authorization: `Bearer ${token}` } : {}) });
const stripeH = (key: string) => ({ Authorization: basic(key, ""), "Content-Type": "application/x-www-form-urlencoded" });
const canvaH = (t: string) => ({ Authorization: `Bearer ${t}` });

// Local Leads (OpenStreetMap). Category words -> OSM tags.
const OSM: Record<string, string[]> = {
  plumber: ['["craft"="plumber"]'], plumbing: ['["craft"="plumber"]'], hvac: ['["craft"="hvac"]'], heating: ['["craft"="hvac"]'],
  electrician: ['["craft"="electrician"]'], roofer: ['["craft"="roofer"]'], roofing: ['["craft"="roofer"]'],
  contractor: ['["craft"="builder"]', '["office"="construction_company"]'], construction: ['["office"="construction_company"]', '["craft"="builder"]'],
  painter: ['["craft"="painter"]'], carpenter: ['["craft"="carpenter"]'], landscaper: ['["craft"="gardener"]'], landscaping: ['["craft"="gardener"]'],
  locksmith: ['["craft"="locksmith"]', '["shop"="locksmith"]'], restaurant: ['["amenity"="restaurant"]'], cafe: ['["amenity"="cafe"]'],
  bakery: ['["shop"="bakery"]'], salon: ['["shop"="hairdresser"]', '["shop"="beauty"]'], hair: ['["shop"="hairdresser"]'],
  barber: ['["shop"="hairdresser"]["name"~"barber",i]', '["hairdresser"="barber"]'], beauty: ['["shop"="beauty"]'], nails: ['["shop"="beauty"]["beauty"~"nails"]'],
  gym: ['["leisure"="fitness_centre"]'], fitness: ['["leisure"="fitness_centre"]'], dentist: ['["amenity"="dentist"]'],
  lawyer: ['["office"="lawyer"]'], attorney: ['["office"="lawyer"]'], "real estate": ['["office"="estate_agent"]'], realtor: ['["office"="estate_agent"]'],
  "auto repair": ['["shop"="car_repair"]'], mechanic: ['["shop"="car_repair"]'], "car wash": ['["amenity"="car_wash"]'],
  church: ['["amenity"="place_of_worship"]'], boutique: ['["shop"="clothes"]', '["shop"="boutique"]'], clothing: ['["shop"="clothes"]'],
  tattoo: ['["shop"="tattoo"]'], florist: ['["shop"="florist"]'], insurance: ['["office"="insurance"]'], accountant: ['["office"="accountant"]'],
  photographer: ['["craft"="photographer"]', '["shop"="photo"]'], "pet grooming": ['["shop"="pet_grooming"]'], daycare: ['["amenity"="childcare"]', '["amenity"="kindergarten"]'],
  cleaning: ['["shop"="dry_cleaning"]', '["office"="cleaning"]', '["craft"="cleaning"]'], spa: ['["leisure"="spa"]', '["shop"="massage"]'],
  "food truck": ['["amenity"="fast_food"]["street_vendor"="yes"]'], "fast food": ['["amenity"="fast_food"]'], bar: ['["amenity"="bar"]', '["amenity"="pub"]'],
  hotel: ['["tourism"="hotel"]', '["tourism"="motel"]'], chiropractor: ['["healthcare"="chiropractor"]', '["healthcare:speciality"="chiropractic"]'],
  "music studio": ['["amenity"="studio"]', '["craft"="sound_studio"]'], studio: ['["amenity"="studio"]', '["craft"="sound_studio"]'],
};
const milesBetween = (a: number, b: number, c: number, d: number) => {
  const R = 3958.8, r = Math.PI / 180, x = Math.sin(((c - a) * r) / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
};

// ---------------------------------------------------------------- actions
type Op = (args: any, row: any) => Promise<unknown>;
const OPS: Record<string, Record<string, Op>> = {
  discord: { async send(a) { return share({ text: need(a.text, "a message"), url: a.url, kind: a.kind, link: a.link }, ["discord"]); } },
  telegram: { async send(a) { return share({ text: need(a.text, "a message"), url: a.url, kind: a.kind, link: a.link }, ["telegram"]); } },
  slack: { async send(a) { return share({ text: need(a.text, "a message"), url: a.url, kind: a.kind, link: a.link }, ["slack"]); } },

  canva: {
    async designs(a) {
      const t = await bearer("canva");
      const u = new URL("https://api.canva.com/rest/v1/designs");
      u.searchParams.set("ownership", "any"); u.searchParams.set("sort_by", "modified_descending");
      if (a.query) u.searchParams.set("query", String(a.query).slice(0, 100));
      if (a.continuation) u.searchParams.set("continuation", String(a.continuation));
      const r = await http(u.toString(), { label: "Canva", headers: canvaH(t) });
      return {
        designs: (r.items ?? []).map((d: any) => ({ id: d.id, title: d.title || "Untitled design", thumb: d.thumbnail?.url, edit: d.urls?.edit_url, view: d.urls?.view_url, updated: d.updated_at, pages: d.page_count })),
        continuation: r.continuation ?? null,
      };
    },
    async export(a) {
      const t = await bearer("canva");
      const id = need(a.design, "a design");
      const fmt = a.format === "mp4" ? { type: "mp4", quality: "vertical_1080p" } : a.format === "png" ? { type: "png" } : { type: "jpg", quality: 92 };
      const job = await http("https://api.canva.com/rest/v1/exports", { method: "POST", label: "Canva", headers: { ...canvaH(t), "Content-Type": "application/json" }, body: JSON.stringify({ design_id: id, format: fmt }) });
      return OPS.canva.export_status({ job: job.job?.id, title: a.title, design: id, format: fmt.type }, null);
    },
    async export_status(a) {
      const t = await bearer("canva");
      const started = Date.now();
      for (;;) {
        const r = await http(`https://api.canva.com/rest/v1/exports/${encodeURIComponent(need(a.job, "the export job"))}`, { label: "Canva", headers: canvaH(t) });
        const j = r.job ?? {};
        if (j.status === "success") {
          const items = [];
          for (const [i, u] of (j.urls ?? []).slice(0, 10).entries()) {
            const k = await keep(u, "canva", `${a.title || "canva"}-${i + 1}`);
            items.push(await addLib({ source: "canva", kind: k.kind, title: `${a.title || "Canva design"}${(j.urls ?? []).length > 1 ? ` (page ${i + 1})` : ""}`, url: k.url, ref: a.design, meta: { format: a.format } }));
          }
          return { done: true, items };
        }
        if (j.status === "failed") throw new Fail(`Canva export failed: ${j.error?.message ?? j.error?.code ?? "unknown"}`, 502);
        if (Date.now() - started > 80000) return { pending: true, job: a.job, title: a.title, design: a.design, format: a.format };
        await sleep(3000);
      }
    },
    async send_to_canva(a) {
      if (a.kind === "video") throw new Fail("Canva's API only starts designs from images. Download the video and drop it into Canva instead.");
      const t = await bearer("canva");
      const src = https(a.url);
      const title = String(a.title || "iRun upload").slice(0, 50);
      const file = await fetch(src, { signal: AbortSignal.timeout(60000) });
      if (!file.ok) throw new Fail(`Could not download the file (${file.status}).`, 502);
      const bytes = new Uint8Array(await file.arrayBuffer());
      const meta = JSON.stringify({ name_base64: btoa(String.fromCharCode(...enc.encode(title))) });
      const up = await http("https://api.canva.com/rest/v1/asset-uploads", {
        method: "POST", label: "Canva", timeout: 60000, headers: { ...canvaH(t), "Content-Type": "application/octet-stream", "Asset-Upload-Metadata": meta }, body: bytes,
      });
      let job = up.job, tries = 0;
      while (job?.status === "in_progress" && tries++ < 25) { await sleep(2000); job = (await http(`https://api.canva.com/rest/v1/asset-uploads/${job.id}`, { label: "Canva", headers: canvaH(t) })).job; }
      if (job?.status !== "success") throw new Fail(`Canva upload ${job?.status === "failed" ? `failed: ${job.error?.message ?? ""}` : "is still processing. Try again in a minute."}`, 502);
      const design = await http("https://api.canva.com/rest/v1/designs", {
        method: "POST", label: "Canva", headers: { ...canvaH(t), "Content-Type": "application/json" },
        body: JSON.stringify({ design_type: { type: "custom", width: 1080, height: 1350 }, asset_id: job.asset.id, title }),
      });
      return { asset: job.asset.id, edit: design.design?.urls?.edit_url, design: design.design?.id };
    },
  },

  figma: {
    async frames(a, row) {
      const key = String(need(a.file, "a Figma file link")).match(/figma\.com\/(?:file|design|proto|board)\/([A-Za-z0-9]+)/)?.[1] ?? String(a.file).trim();
      const r = await http(`https://api.figma.com/v1/files/${key}?depth=2`, { label: "Figma", timeout: 40000, headers: { "X-Figma-Token": row.creds.token } });
      const frames: any[] = [];
      for (const page of r.document?.children ?? []) for (const n of page.children ?? []) {
        if (["FRAME", "COMPONENT", "COMPONENT_SET", "SECTION", "GROUP"].includes(n.type)) frames.push({ id: n.id, name: n.name, page: page.name });
      }
      const list = frames.slice(0, 60);
      if (list.length) {
        try {
          const th = await http(`https://api.figma.com/v1/images/${key}?ids=${encodeURIComponent(list.slice(0, 40).map((f) => f.id).join(","))}&format=jpg&scale=0.3`, { label: "Figma", timeout: 40000, headers: { "X-Figma-Token": row.creds.token } });
          for (const f of list) f.thumb = th.images?.[f.id] ?? null;
        } catch { /* thumbnails are optional */ }
      }
      return { file: key, name: r.name, frames: list };
    },
    async export(a, row) {
      const key = need(a.file, "the file"), node = need(a.node, "a frame");
      const r = await http(`https://api.figma.com/v1/images/${key}?ids=${encodeURIComponent(node)}&format=jpg&scale=2`, { label: "Figma", timeout: 50000, headers: { "X-Figma-Token": row.creds.token } });
      const u = r.images?.[node];
      if (!u) throw new Fail("Figma could not render that frame.", 502);
      const k = await keep(u, "figma", a.name || "figma");
      return { item: await addLib({ source: "figma", kind: "image", title: a.name || "Figma frame", url: k.url, ref: `${key}:${node}` }) };
    },
  },

  shopify: {
    async products(_a, row) {
      const store = row.creds.store;
      const r = await http(`https://${store}/products.json?limit=250`, { label: "Shopify", timeout: 30000 });
      return {
        store,
        products: (r.products ?? []).map((p: any) => ({
          id: p.id, title: p.title, handle: p.handle, price: p.variants?.[0]?.price, type: p.product_type,
          image: p.images?.[0]?.src, images: (p.images ?? []).slice(0, 6).map((i: any) => i.src), url: `https://${store}/products/${p.handle}`,
          available: (p.variants ?? []).some((v: any) => v.available),
        })),
      };
    },
    async import(a) {
      const src = https(a.image);
      const k = await keep(src, "shopify", a.title || "product");
      return { item: await addLib({ source: "shopify", kind: "image", title: a.title || "Product photo", url: k.url, ref: a.handle, meta: { product_url: a.url, price: a.price } }) };
    },
    async sales(a, row) {
      if (!row.creds.token) throw new Fail("Add an Admin API token on the Shopify card to see sales.");
      const days = Math.max(1, Math.min(60, Number(a.days) || 30));
      const since = new Date(Date.now() - days * 86400000).toISOString();
      let after: string | null = null, orders = 0, revenue = 0, currency = "USD";
      for (let page = 0; page < 8; page++) {
        const d: any = await shopGql(row.creds, `query($q:String!,$after:String){ orders(first:250, query:$q, after:$after){ pageInfo{hasNextPage endCursor} edges{ node{ currentTotalPriceSet{ shopMoney{ amount currencyCode } } } } } }`, { q: `created_at:>=${since}`, after });
        for (const e of d.orders.edges) { orders++; revenue += Number(e.node.currentTotalPriceSet.shopMoney.amount); currency = e.node.currentTotalPriceSet.shopMoney.currencyCode; }
        if (!d.orders.pageInfo.hasNextPage) break;
        after = d.orders.pageInfo.endCursor;
      }
      return { days, orders, revenue: Math.round(revenue * 100) / 100, currency };
    },
    async make_ad(a) {
      const url = https(a.url);
      const g = await getInt("github");
      if (!g?.creds?.token) throw new Fail("Connect GitHub with a token first. The ad renders on iRun's GitHub autopilot.");
      await http(`https://api.github.com/repos/${IRUN_REPO}/actions/workflows/shopify-ad.yml/dispatches`, {
        method: "POST", label: "GitHub", headers: { ...gh(g.creds.token), "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "main", inputs: { product: url, store: new URL(url).hostname, account: IG_ACCOUNT, post: "false" } }),
      });
      return { started: true, note: "The ad is rendering on iRun's autopilot. It shows in your Command dashboard when it's done." };
    },
  },

  stripe: {
    async revenue(a, row) {
      const key = row.creds.key;
      const days = Math.max(1, Math.min(90, Number(a.days) || 30));
      const bal = await http("https://api.stripe.com/v1/balance", { label: "Stripe", headers: stripeH(key) });
      const since = Math.floor(Date.now() / 1000) - days * 86400;
      const totals: Record<string, { gross: number; count: number }> = {};
      let starting: string | null = null;
      for (let page = 0; page < 5; page++) {
        const q = new URLSearchParams({ limit: "100", "created[gte]": String(since) });
        if (starting) q.set("starting_after", starting);
        const r = await http(`https://api.stripe.com/v1/charges?${q}`, { label: "Stripe", headers: stripeH(key) });
        for (const c of r.data ?? []) {
          if (!c.paid || c.status !== "succeeded") continue;
          const t = (totals[c.currency] ??= { gross: 0, count: 0 });
          t.gross += (c.amount - (c.amount_refunded ?? 0)) / 100; t.count++;
        }
        if (!r.has_more || !r.data?.length) break;
        starting = r.data[r.data.length - 1].id;
      }
      return {
        days,
        available: (bal.available ?? []).map((b: any) => ({ amount: b.amount / 100, currency: b.currency })),
        pending: (bal.pending ?? []).map((b: any) => ({ amount: b.amount / 100, currency: b.currency })),
        charges: Object.entries(totals).map(([currency, t]) => ({ currency, gross: Math.round(t.gross * 100) / 100, count: t.count })),
      };
    },
    async payment_link(a, row) {
      const name = need(a.name, "what you're selling").slice(0, 120);
      const cents = Math.round(Number(a.amount) * 100);
      if (!Number.isFinite(cents) || cents < 50) throw new Fail("Add a price of at least $0.50.");
      const q = new URLSearchParams({ currency: String(a.currency || "usd").toLowerCase(), unit_amount: String(cents), "product_data[name]": name });
      if (a.interval === "month" || a.interval === "year" || a.interval === "week") q.set("recurring[interval]", a.interval);
      const price = await http("https://api.stripe.com/v1/prices", { method: "POST", label: "Stripe", headers: stripeH(row.creds.key), body: q });
      const link = await http("https://api.stripe.com/v1/payment_links", {
        method: "POST", label: "Stripe", headers: stripeH(row.creds.key),
        body: new URLSearchParams({ "line_items[0][price]": price.id, "line_items[0][quantity]": "1" }),
      });
      const links = [{ name, amount: cents / 100, interval: a.interval || null, url: link.url, id: link.id, at: nowIso() }, ...(row.meta?.links ?? [])].slice(0, 25);
      await patchInt("stripe", { meta: { ...row.meta, links } });
      return { url: link.url, id: link.id, links };
    },
    async links(_a, row) { return { links: row.meta?.links ?? [] }; },
  },

  hubspot: {
    async count(_a, row) {
      const r = await http("https://api.hubapi.com/crm/v3/objects/contacts/search", {
        method: "POST", label: "HubSpot", headers: { Authorization: `Bearer ${row.creds.token}`, "Content-Type": "application/json" }, body: JSON.stringify({ limit: 1 }),
      });
      return { contacts: r.total ?? 0, last_sync: row.meta?.last_sync ?? null, synced: row.meta?.synced ?? 0 };
    },
    async sync(_a, row) { return hubspotSync(row); },
    async add(a, row) {
      const rows = (Array.isArray(a.rows) ? a.rows : []).slice(0, 100);
      if (!rows.length) throw new Fail("Pick some leads first.");
      return hubspotCreate(row.creds.token, rows.map((l: any) => ({
        email: l.email || undefined, company: l.name || l.business, phone: l.phone || undefined, website: l.website || undefined,
        city: l.city || undefined, address: l.address || undefined,
      })));
    },
  },

  calendly: {
    async events(_a, row) {
      const u = new URL("https://api.calendly.com/scheduled_events");
      u.searchParams.set("user", row.meta?.user); u.searchParams.set("status", "active"); u.searchParams.set("sort", "start_time:asc");
      u.searchParams.set("min_start_time", nowIso()); u.searchParams.set("count", "20");
      const r = await http(u.toString(), { label: "Calendly", headers: { Authorization: `Bearer ${row.creds.token}` } });
      return { link: row.meta?.scheduling_url, events: (r.collection ?? []).map((e: any) => ({ name: e.name, start: e.start_time, end: e.end_time, where: e.location?.join_url || e.location?.location || e.location?.type })) };
    },
  },

  zoom: {
    async meeting(a, row) {
      const t = await zoomToken(row.creds);
      const body: any = { topic: String(a.topic || "HSW365 call").slice(0, 200), type: a.start ? 2 : 1, duration: Math.max(15, Math.min(240, Number(a.minutes) || 30)),
        settings: { join_before_host: true, waiting_room: false } };
      if (a.start) { body.start_time = new Date(a.start).toISOString().replace(/\.\d+Z$/, "Z"); body.timezone = "America/New_York"; }
      const m = await http("https://api.zoom.us/v2/users/me/meetings", { method: "POST", label: "Zoom", headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return { join: m.join_url, start: m.start_url, id: m.id, passcode: m.password, when: m.start_time ?? null, topic: m.topic };
    },
    async meetings(_a, row) {
      const t = await zoomToken(row.creds);
      const r = await http("https://api.zoom.us/v2/users/me/meetings?type=upcoming&page_size=20", { label: "Zoom", headers: { Authorization: `Bearer ${t}` } });
      return { meetings: (r.meetings ?? []).map((m: any) => ({ topic: m.topic, start: m.start_time, join: m.join_url, id: m.id })) };
    },
  },

  leads: {
    async search(a) {
      const what = need(a.what, "a kind of business").toLowerCase().slice(0, 40);
      const where = need(a.where, "a city or ZIP").slice(0, 80);
      const miles = Math.max(1, Math.min(40, Number(a.miles) || 15));
      const geo = await http(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=us&q=${encodeURIComponent(where)}`, { label: "OpenStreetMap" });
      if (!geo?.[0]) throw new Fail(`Couldn't find "${where}". Try a city and state, like Vineland NJ.`);
      const lat = Number(geo[0].lat), lon = Number(geo[0].lon), R = Math.round(miles * 1609.34);
      const safe = what.replace(/[^a-z0-9 &'-]/g, "");
      const tags = OSM[what] ?? OSM[Object.keys(OSM).find((k) => what.includes(k)) ?? ""] ?? [`["name"~"${safe}",i]`];
      const q = `[out:json][timeout:25];(${tags.map((t) => `nwr${t}(around:${R},${lat},${lon});`).join("")});out center tags 300;`;
      const r = await http("https://overpass-api.de/api/interpreter", { method: "POST", label: "OpenStreetMap", timeout: 40000, headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ data: q }) });
      const seen = new Set<string>();
      const rows = (r.elements ?? []).map((e: any) => {
        const t = e.tags ?? {}, la = e.lat ?? e.center?.lat, lo = e.lon ?? e.center?.lon;
        const addr = [t["addr:housenumber"], t["addr:street"]].filter(Boolean).join(" ");
        return {
          name: t.name || t.brand || "", phone: t.phone || t["contact:phone"] || "", email: (t.email || t["contact:email"] || "").toLowerCase(),
          website: t.website || t["contact:website"] || t.url || "", address: addr, city: t["addr:city"] || "", state: t["addr:state"] || "",
          instagram: t["contact:instagram"] || "", facebook: t["contact:facebook"] || "",
          miles: la && lo ? Math.round(milesBetween(lat, lon, la, lo) * 10) / 10 : null, osm: `${e.type}/${e.id}`,
        };
      }).filter((l: any) => l.name && !seen.has(l.name.toLowerCase() + l.address) && seen.add(l.name.toLowerCase() + l.address))
        .sort((x: any, y: any) => (Number(!!y.email) * 4 + Number(!!y.website) * 2 + Number(!!y.phone)) - (Number(!!x.email) * 4 + Number(!!x.website) * 2 + Number(!!x.phone)) || (x.miles ?? 99) - (y.miles ?? 99));
      return { center: { lat, lon, label: geo[0].display_name }, what, miles, count: rows.length, leads: rows.slice(0, 200) };
    },
    async to_sales(a) {
      const rows = (Array.isArray(a.rows) ? a.rows : []).filter((l: any) => /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(l.email ?? "")).slice(0, 200);
      if (!rows.length) throw new Fail("None of those leads has an email address. Send them to HubSpot or download the list instead.");
      const emails = rows.map((l: any) => l.email.toLowerCase());
      const { data: have } = await db.from("irun_sales_leads").select("email").in("email", emails);
      const { data: off } = await db.from("irun_suppress").select("email").in("email", emails);
      const skip = new Set([...(have ?? []), ...(off ?? [])].map((x: any) => x.email));
      const fresh = rows.filter((l: any) => !skip.has(l.email.toLowerCase())).map((l: any) => ({
        email: l.email.toLowerCase(), business: l.name, trade: String(a.what || "").toLowerCase() || null, city: l.city || null, state: l.state || null,
        website: l.website || null, source: "irun-connect:openstreetmap", status: "draft", note: "Found with iRun Connect Local Leads. Approve it in the Sales Agent to send.",
      }));
      if (fresh.length) { const { error } = await db.from("irun_sales_leads").insert(fresh); if (error) throw new Fail(`Sales Agent: ${error.message}`, 500); }
      return { added: fresh.length, skipped: rows.length - fresh.length };
    },
  },

  instagram: {
    async overview() {
      const token = await igToken();
      const me = await igCall("/me", token, { fields: "user_id,username,name,followers_count,follows_count,media_count,profile_picture_url" });
      const until = Math.floor(Date.now() / 1000), since = until - 28 * 86400;
      const totals: Record<string, number> = {};
      await Promise.allSettled(["reach", "views", "profile_views", "accounts_engaged", "total_interactions", "website_clicks", "follows_and_unfollows"].map(async (m) => {
        const r = await igCall("/me/insights", token, { metric: m, period: "day", metric_type: "total_value", since: String(since), until: String(until) });
        const v = r.data?.[0]?.total_value?.value;
        if (typeof v === "number") totals[m] = v;
      }));
      const media = await igCall("/me/media", token, { fields: "id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,timestamp,like_count,comments_count", limit: "12" });
      const posts = await Promise.all((media.data ?? []).map(async (p: any) => {
        const out: any = { id: p.id, caption: (p.caption ?? "").slice(0, 140), type: p.media_product_type || p.media_type, link: p.permalink, thumb: p.thumbnail_url || p.media_url, at: p.timestamp, likes: p.like_count ?? 0, comments: p.comments_count ?? 0 };
        try {
          const r = await igCall(`/${p.id}/insights`, token, { metric: "views,reach,saved,shares,total_interactions" });
          for (const d of r.data ?? []) out[d.name] = d.values?.[0]?.value ?? d.total_value?.value ?? 0;
        } catch { /* older posts may not have every metric */ }
        return out;
      }));
      return { account: { username: me.username, name: me.name, followers: me.followers_count, following: me.follows_count, posts: me.media_count, picture: me.profile_picture_url }, last28: totals, posts };
    },
  },

  spotify: {
    async artist(a, row) {
      const t = await spotifyToken(row.creds);
      const q = String(a.q || row.meta?.artist || "HOODSTAR365").slice(0, 80);
      const r = await http(`https://api.spotify.com/v1/search?type=artist&limit=6&q=${encodeURIComponent(q)}`, { label: "Spotify", headers: { Authorization: `Bearer ${t}` } });
      return { artists: (r.artists?.items ?? []).map((x: any) => ({ id: x.id, name: x.name, followers: x.followers?.total ?? null, popularity: x.popularity ?? null, image: x.images?.[0]?.url, link: x.external_urls?.spotify, genres: x.genres ?? [] })) };
    },
    async music(a, row) {
      const t = await spotifyToken(row.creds);
      const id = need(a.artist, "an artist");
      const H = { Authorization: `Bearer ${t}` };
      const [top, albums] = await Promise.allSettled([
        http(`https://api.spotify.com/v1/artists/${id}/top-tracks?market=US`, { label: "Spotify", headers: H }),
        http(`https://api.spotify.com/v1/artists/${id}/albums?include_groups=album,single&market=US&limit=20`, { label: "Spotify", headers: H }),
      ]);
      if (a.save_artist) await patchInt("spotify", { meta: { ...row.meta, artist: a.save_artist, artist_id: id } });
      return {
        tracks: top.status === "fulfilled" ? (top.value.tracks ?? []).map((x: any) => ({ id: x.id, name: x.name, album: x.album?.name, image: x.album?.images?.[0]?.url, link: x.external_urls?.spotify, popularity: x.popularity, released: x.album?.release_date })) : [],
        releases: albums.status === "fulfilled" ? (albums.value.items ?? []).map((x: any) => ({ id: x.id, name: x.name, type: x.album_type, image: x.images?.[0]?.url, link: x.external_urls?.spotify, released: x.release_date, tracks: x.total_tracks })) : [],
      };
    },
    async import(a) {
      const k = await keep(https(a.image), "spotify", a.title || "cover");
      return { item: await addLib({ source: "spotify", kind: "image", title: a.title || "Cover art", url: k.url, ref: a.ref, meta: { link: a.link } }) };
    },
  },

  github: {
    async repos(_a, row) {
      const { token, owner } = row.creds;
      const url = token ? "https://api.github.com/user/repos?affiliation=owner&per_page=100&sort=pushed" : `https://api.github.com/users/${encodeURIComponent(owner)}/repos?per_page=100&sort=pushed`;
      const r = await http(url, { label: "GitHub", headers: gh(token) });
      let known = "";
      try {
        const f = await http(`https://api.github.com/repos/${IRUN_REPO}/contents/config/capabilities.json`, { label: "GitHub", headers: { ...gh(token), Accept: "application/vnd.github.raw+json" } });
        known = (typeof f === "string" ? f : JSON.stringify(f)).toLowerCase();
      } catch { /* optional */ }
      return {
        repos: (r ?? []).filter((x: any) => !x.fork && !x.archived).map((x: any) => {
          const pages = x.has_pages ? `https://${x.owner.login.toLowerCase()}.github.io/${x.name}/` : "";
          const live = x.homepage || pages;
          return { name: x.name, description: x.description, private: x.private, pushed: x.pushed_at, link: x.html_url, live,
            in_irun: !!known && (known.includes(`github.io/${x.name.toLowerCase()}`) || (!!x.homepage && known.includes(String(x.homepage).toLowerCase().replace(/\/$/, "")))) };
        }),
      };
    },
    async runs(_a, row) {
      if (!row.creds.token) throw new Fail("Add a GitHub token to see and run iRun's autopilot.");
      const r = await http(`https://api.github.com/repos/${IRUN_REPO}/actions/runs?per_page=15`, { label: "GitHub", headers: gh(row.creds.token) });
      return { runs: (r.workflow_runs ?? []).map((x: any) => ({ name: x.name, status: x.status, result: x.conclusion, at: x.created_at, link: x.html_url, event: x.event })) };
    },
    async dispatch(a, row) {
      if (!row.creds.token) throw new Fail("Add a GitHub token with Actions write access to run iRun's autopilot.");
      const allowed: Record<string, string[]> = {
        "daily.yml": ["count", "app", "cap", "mode"], "irun.yml": ["platform", "account", "product", "mode", "kind", "idea", "style"],
        "shopify-ad.yml": ["product", "store", "account", "post"], "sales.yml": ["task", "offer"], "showcase.yml": ["apps"],
        "operator.yml": ["task", "company", "mode"], "shopteam.yml": ["company", "now", "mode"],
      };
      const wf = need(a.workflow, "a workflow");
      if (!allowed[wf]) throw new Fail("That workflow can't be started from here.");
      const inputs: Record<string, string> = {};
      for (const [k, v] of Object.entries(a.inputs ?? {})) if (allowed[wf].includes(k) && String(v ?? "").trim() !== "") inputs[k] = String(v).slice(0, 500);
      await http(`https://api.github.com/repos/${IRUN_REPO}/actions/workflows/${wf}/dispatches`, {
        method: "POST", label: "GitHub", headers: { ...gh(row.creds.token), "Content-Type": "application/json" }, body: JSON.stringify({ ref: "main", inputs }),
      });
      return { started: true, workflow: wf, inputs };
    },
  },

  render: {
    async services(_a, row) {
      const H = { Authorization: `Bearer ${row.creds.key}`, Accept: "application/json" };
      const r = await http("https://api.render.com/v1/services?limit=50", { label: "Render", headers: H });
      const list = (r ?? []).map((x: any) => x.service).filter(Boolean);
      return {
        services: await Promise.all(list.map(async (s: any) => {
          let deploy: any = null;
          try { deploy = (await http(`https://api.render.com/v1/services/${s.id}/deploys?limit=1`, { label: "Render", headers: H }))?.[0]?.deploy ?? null; } catch { /* optional */ }
          return { id: s.id, name: s.name, type: s.type, suspended: s.suspended, url: s.serviceDetails?.url || null, repo: s.repo, updated: s.updatedAt,
            deploy: deploy ? { status: deploy.status, at: deploy.finishedAt || deploy.createdAt } : null };
        })),
      };
    },
    async deploy(a, row) {
      const id = need(a.service, "a service");
      const r = await http(`https://api.render.com/v1/services/${encodeURIComponent(id)}/deploys`, { method: "POST", label: "Render", headers: { Authorization: `Bearer ${row.creds.key}`, Accept: "application/json", "Content-Type": "application/json" }, body: "{}" });
      return { id: r.id, status: r.status };
    },
  },

  gdrive: {
    async folder() {
      const t = await bearer("gdrive");
      const row = await getInt("gdrive");
      if (row.meta?.folder) return row.meta.folder as string;
      const q = encodeURIComponent("name='iRun' and mimeType='application/vnd.google-apps.folder' and trashed=false");
      const f = await http(`https://www.googleapis.com/drive/v3/files?q=${q}&fields=files(id)`, { label: "Google Drive", headers: { Authorization: `Bearer ${t}` } });
      let id = f.files?.[0]?.id;
      if (!id) id = (await http("https://www.googleapis.com/drive/v3/files?fields=id", { method: "POST", label: "Google Drive", headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }, body: JSON.stringify({ name: "iRun", mimeType: "application/vnd.google-apps.folder" }) })).id;
      await patchInt("gdrive", { meta: { ...row.meta, folder: id } });
      return id;
    },
    async save(a) {
      const src = https(a.url);
      const folder = await OPS.gdrive.folder({}, null) as string;
      const t = await bearer("gdrive");
      const file = await fetch(src, { signal: AbortSignal.timeout(90000) });
      if (!file.ok) throw new Fail(`Could not download the file (${file.status}).`, 502);
      const type = (file.headers.get("content-type") || "application/octet-stream").split(";")[0];
      const bytes = new Uint8Array(await file.arrayBuffer());
      const ext = type.includes("mp4") ? ".mp4" : type.includes("png") ? ".png" : type.includes("jpeg") ? ".jpg" : type.includes("webp") ? ".webp" : "";
      const name = `${String(a.name || "iRun").replace(/[\\/:*?"<>|]+/g, " ").slice(0, 80)}${ext}`;
      const boundary = "irun" + rand(9);
      const head = enc.encode(`--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify({ name, parents: [folder] })}\r\n--${boundary}\r\nContent-Type: ${type}\r\n\r\n`);
      const tail = enc.encode(`\r\n--${boundary}--`);
      const body = new Uint8Array(head.length + bytes.length + tail.length);
      body.set(head); body.set(bytes, head.length); body.set(tail, head.length + bytes.length);
      const r = await http("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink", {
        method: "POST", label: "Google Drive", timeout: 90000, headers: { Authorization: `Bearer ${t}`, "Content-Type": `multipart/related; boundary=${boundary}` }, body,
      });
      await markPosted(a.lib, { to: "gdrive", id: r.id, link: r.webViewLink });
      return { id: r.id, name: r.name, link: r.webViewLink };
    },
    async files() {
      const folder = await OPS.gdrive.folder({}, null) as string;
      const t = await bearer("gdrive");
      const q = encodeURIComponent(`'${folder}' in parents and trashed=false`);
      const r = await http(`https://www.googleapis.com/drive/v3/files?q=${q}&orderBy=createdTime desc&pageSize=30&fields=files(id,name,webViewLink,thumbnailLink,createdTime,mimeType)`, { label: "Google Drive", headers: { Authorization: `Bearer ${t}` } });
      return { files: r.files ?? [] };
    },
  },

  domains: {
    async check(a) {
      const raw = String(need(a.names, "a name to check")).toLowerCase().split(/[,;\n]+/)
        .map((s) => s.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/^www\./, "").replace(/\s+/g, "")).filter(Boolean);
      const list: string[] = [];
      for (const n of raw) {
        if (/\.[a-z]{2,}$/.test(n)) list.push(n);
        else { const base = n.replace(/[^a-z0-9-]/g, ""); if (base) list.push(`${base}.com`, `${base}.net`, `${base}.co`); }
      }
      const uniq = [...new Set(list)].slice(0, 15);
      const results = await Promise.all(uniq.map(async (d) => {
        try {
          const r = await fetch(`https://rdap.org/domain/${encodeURIComponent(d)}`, { headers: { Accept: "application/rdap+json", "User-Agent": UA }, redirect: "follow", signal: AbortSignal.timeout(15000) });
          if (r.status === 404) return { domain: d, available: true };
          if (!r.ok) return { domain: d, available: null, note: `lookup returned ${r.status}` };
          const j = await r.json().catch(() => ({}));
          const exp = (j.events ?? []).find((e: any) => e.eventAction === "expiration")?.eventDate ?? null;
          return { domain: d, available: false, expires: exp };
        } catch { return { domain: d, available: null, note: "lookup timed out" }; }
      }));
      return { results };
    },
  },
};

async function hubspotCreate(token: string, people: any[]) {
  const withEmail = people.filter((p) => p.email);
  const without = people.filter((p) => !p.email);
  let created = 0, updated = 0;
  const H = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const clean = (o: any) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== ""));
  for (let i = 0; i < withEmail.length; i += 100) {
    const r = await http("https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert", {
      method: "POST", label: "HubSpot", headers: H, body: JSON.stringify({ inputs: withEmail.slice(i, i + 100).map((p) => ({ idProperty: "email", id: p.email, properties: clean(p) })) }),
    });
    for (const x of r.results ?? []) x.new ? created++ : updated++;
  }
  for (let i = 0; i < without.length; i += 100) {
    const r = await http("https://api.hubapi.com/crm/v3/objects/contacts/batch/create", {
      method: "POST", label: "HubSpot", headers: H, body: JSON.stringify({ inputs: without.slice(i, i + 100).map((p) => ({ properties: clean(p) })) }),
    });
    created += (r.results ?? []).length;
  }
  return { created, updated };
}
// New iRun leads since the last sync: Instagram comment/DM leads and Sales Agent leads that replied or are hot.
async function hubspotSync(row: any) {
  const since = row.meta?.last_sync ?? new Date(Date.now() - 30 * 86400000).toISOString();
  const started = nowIso();
  const { data: ig } = await db.from("irun_leads").select("username,keyword,product_id,message,created_at").gt("created_at", since).limit(500);
  const { data: sales } = await db.from("irun_sales_leads").select("email,business,contact,city,state,website,status,created_at").in("status", ["hot", "needs_owner", "replied"]).gt("created_at", since).limit(500);
  const people = [
    ...(ig ?? []).filter((l: any) => l.username).map((l: any) => ({ firstname: `@${l.username}`, lastname: "(Instagram)", jobtitle: `Asked about ${l.product_id || l.keyword || "HSW365"}` })),
    ...(sales ?? []).map((l: any) => {
      const [first, ...rest] = String(l.contact ?? "").trim().split(/\s+/);
      return { email: l.email, company: l.business, firstname: first || undefined, lastname: rest.join(" ") || undefined, city: l.city, state: l.state, website: l.website };
    }),
  ];
  const res = people.length ? await hubspotCreate(row.creds.token, people) : { created: 0, updated: 0 };
  await patchInt("hubspot", { meta: { ...row.meta, last_sync: started, synced: (row.meta?.synced ?? 0) + res.created + res.updated }, last_error: null });
  return { ...res, instagram: (ig ?? []).length, sales: (sales ?? []).length, since };
}

// ---------------------------------------------------------------- router
async function catalog() {
  const { data } = await db.from("irun_integrations").select("*");
  const rows = new Map((data ?? []).map((r: any) => [r.id, r]));
  let ig: any = null;
  try {
    const { data: t } = await db.from("irun_tokens").select("expires_at,updated_at").eq("name", `instagram:${IG_ACCOUNT}`).maybeSingle();
    ig = t;
  } catch { /* table always exists */ }
  const { count } = await db.from("irun_library").select("id", { count: "exact", head: true });
  return {
    redirect: REDIRECT,
    library: count ?? 0,
    items: IDS.map((id) => {
      if (FREE.has(id)) return { id, connected: true, free: true };
      if (id === "instagram") return { id, connected: !!ig, label: ig ? "@hoodstar365" : "", expires: ig?.expires_at ?? null };
      const r: any = rows.get(id);
      if (!r) return { id, connected: false };
      const hints: Record<string, string> = {};
      for (const [k, v] of Object.entries(r.creds ?? {})) if (!["access_token", "refresh_token", "expires_at"].includes(k)) hints[k] = ["store", "admin", "owner", "chat"].includes(k) ? String(v) : mask(v);
      const meta = { ...(r.meta ?? {}) }; delete meta.oauth;
      return { id, connected: r.status === "connected", pending: r.status === "pending", label: meta.label ?? "", hints, meta, auto_share: r.auto_share, lead_alerts: r.lead_alerts, last_error: r.last_error, connected_at: r.connected_at };
    }),
  };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  if (req.method !== "POST") return json({ error: "Use POST." }, 405);
  try {
    const body = await req.json().catch(() => ({}));
    const key = await setting("owner_key");
    if (!key || String(body.owner ?? "") !== key) return json({ error: "Sign in to iRun with your owner key first." }, 401);
    const a = String(body.a ?? "");
    const id = String(body.id ?? "");
    if (["save", "settings", "disconnect", "oauth_start", "run"].includes(a) && !(IDS as readonly string[]).includes(id)) throw new Fail("Unknown integration.");

    switch (a) {
      case "catalog": return json(await catalog());
      case "save": {
        if (FREE.has(id) || id === "instagram") throw new Fail("Nothing to save for that one.");
        if (OAUTH[id]) throw new Fail("That one connects with a sign-in. Use Connect.");
        const prev = await getInt(id);
        const input = { ...(prev?.creds ?? {}), ...Object.fromEntries(Object.entries(body.creds ?? {}).filter(([, v]) => String(v ?? "").trim() !== "")) };
        const v = await VERIFY[id](input);
        await putInt(id, { creds: v.creds, meta: { ...(prev?.meta ?? {}), ...(v.meta ?? {}), label: v.label }, status: "connected", last_error: null, connected_at: prev?.connected_at ?? nowIso() });
        return json({ ok: true, label: v.label });
      }
      case "settings": {
        const row = await creds(id);
        const patch: Record<string, unknown> = {};
        if (typeof body.auto_share === "boolean") patch.auto_share = SHARE.includes(id) ? body.auto_share : false;
        if (typeof body.lead_alerts === "boolean") patch.lead_alerts = SHARE.includes(id) ? body.lead_alerts : false;
        if (body.meta && typeof body.meta === "object") {
          const allowed = ["use_in_sales", "artist", "auto_sync"];
          patch.meta = { ...row.meta, ...Object.fromEntries(Object.entries(body.meta).filter(([k]) => allowed.includes(k))) };
        }
        await patchInt(id, patch);
        return json({ ok: true });
      }
      case "disconnect": {
        await db.from("irun_integrations").delete().eq("id", id);
        return json({ ok: true });
      }
      case "oauth_start": return json(await oauthStart(id, body.creds));
      case "oauth_finish": return json(await oauthFinish(need(body.code, "the sign-in code"), need(body.state, "the sign-in state")));
      case "run": {
        const op = OPS[id]?.[String(body.op ?? "")];
        if (!op) throw new Fail("Unknown action.");
        const row = FREE.has(id) || id === "instagram" || OAUTH[id] ? await getInt(id) : await creds(id);
        try {
          const out = await op(body.args ?? {}, row);
          if (row && row.last_error) await patchInt(id, { last_error: null });
          return json(out);
        } catch (e) {
          if (row && e instanceof Fail && e.status >= 500) await patchInt(id, { last_error: e.message.slice(0, 300) });
          throw e;
        }
      }
      case "library": {
        const { data } = await db.from("irun_library").select("*").order("created_at", { ascending: false }).limit(Math.min(200, Number(body.limit) || 60));
        // iRun's own latest videos, so they can be shared or saved to Drive from the same place.
        const { data: made } = await db.from("irun_posts").select("id,created_at,caption,hook,video_url,platform,status,account")
          .not("video_url", "is", null).order("created_at", { ascending: false }).limit(12);
        return json({ items: data ?? [], recent: (made ?? []).filter((p: any) => /^https:\/\//.test(p.video_url ?? "")) });
      }
      case "library_add": {
        const url = https(body.url);
        return json({ item: await addLib({ source: String(body.source || "upload").slice(0, 20), kind: body.kind === "video" ? "video" : "image", title: String(body.title || "Upload").slice(0, 120), url }) });
      }
      case "library_del": {
        await db.from("irun_library").delete().eq("id", body.lib);
        return json({ ok: true });
      }
      case "upload_url": {
        const type = String(body.type ?? "");
        if (!/^(image\/(jpeg|png|webp)|video\/mp4)$/.test(type)) throw new Fail("Upload a JPEG, PNG, WebP or MP4.");
        const ext = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "video/mp4": "mp4" }[type];
        const safe = String(body.name ?? "upload").toLowerCase().replace(/\.[a-z0-9]+$/, "").replace(/[^a-z0-9]+/g, "-").slice(0, 50) || "upload";
        const path = `uploads/${Date.now().toString(36)}-${safe}.${ext}`;
        const { data, error } = await db.storage.from(BUCKET).createSignedUploadUrl(path);
        if (error) throw new Fail(`Storage: ${error.message}`, 500);
        return json({ upload: data.signedUrl, path, url: db.storage.from(BUCKET).getPublicUrl(path).data.publicUrl });
      }
      case "share": return json({ shared: await share({ text: need(body.text, "a message"), url: body.url, kind: body.kind, link: body.link }, Array.isArray(body.to) ? body.to : undefined) });
      case "ig_publish": return json(await igPublish(body));
      case "ig_finish": return json(await igFinish({ ...body, container: need(body.container, "the post") }));
      default: throw new Fail("Unknown request.");
    }
  } catch (e) {
    if (e instanceof Fail) return json({ error: e.message }, e.status);
    console.error("irun-connect", e);
    return json({ error: e instanceof Error ? e.message : "iRun Connect failed." }, 500);
  }
});
