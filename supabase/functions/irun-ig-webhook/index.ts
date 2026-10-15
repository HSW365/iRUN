// iRun Instagram lead bot + owner data API.
// - GET  ?hub.mode=subscribe&hub.verify_token=..&hub.challenge=..  -> Meta webhook verification
// - POST (Meta webhook): comment "KEYWORD" -> private-reply DM with the link; DM "KEYWORD" -> reply with link. Every lead logged.
// - GET  ?view=data&key=OWNER_KEY -> JSON for the owner dashboard (dashboard.html)
// - POST {owner:KEY, a:"add_company"|"company"|"prospects"|"credits", ...} -> Operator controls (dashboard.html)
// - GET  ?view=unsub&c=..&e=..&t=..  -> one-click unsubscribe from Operator outreach email (also POST, RFC 8058)
// - Optional AI replies: with secret ANTHROPIC_API_KEY set and irun_settings.ai_dm_replies = on, a DM without a
//   keyword gets a short, factual answer built only from the product list, and is still logged for a human.
import { createClient } from "npm:@supabase/supabase-js@2";

const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const GRAPH = "https://graph.instagram.com/v23.0";
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};
const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });

async function setting(key: string): Promise<string | null> {
  const { data } = await sb.from("irun_settings").select("value").eq("key", key).maybeSingle();
  return data?.value ?? null;
}

async function igToken(): Promise<string | null> {
  const { data } = await sb.from("irun_tokens").select("value").eq("name", "instagram").maybeSingle();
  return data?.value ?? null;
}

async function validSignature(req: Request, raw: string): Promise<boolean> {
  const secret = await setting("ig_app_secret");
  if (!secret) return true; // set ig_app_secret in irun_settings to enforce
  const sig = req.headers.get("x-hub-signature-256") || "";
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(raw)));
  const hex = Array.from(mac).map((b) => b.toString(16).padStart(2, "0")).join("");
  return sig === `sha256=${hex}`;
}

type Product = { id: string; name: string; keyword: string; link: string; pitch: string | null };

async function products(): Promise<Product[]> {
  const { data } = await sb.from("irun_products").select("id,name,keyword,link,pitch").eq("active", true);
  return (data ?? []) as Product[];
}

function match(text: string, list: Product[]): Product | null {
  const t = ` ${text.toUpperCase().replace(/[^A-Z0-9 ]/g, " ")} `;
  return list.find((p) => t.includes(` ${p.keyword.toUpperCase()} `)) ?? null;
}

function replyText(p: Product, username?: string) {
  const hi = username ? `Yo @${username}, appreciate you.` : "Appreciate you reaching out.";
  const what = p.pitch ? ` ${p.pitch}` : "";
  return `${hi} Here's ${p.name}: ${p.link}${what}\n\nAny questions, reply right here. - Hoodstar365 | HSW365 Media`;
}

async function recentlySent(uid: string, pid: string) {
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const { data } = await sb.from("irun_leads").select("id").eq("ig_user_id", uid).eq("product_id", pid)
    .eq("replied", true).gte("created_at", since).limit(1);
  return (data ?? []).length > 0;
}

async function send(recipient: Record<string, string>, text: string): Promise<string | null> {
  const tok = await igToken();
  if (!tok) return "no instagram token stored";
  const r = await fetch(`${GRAPH}/me/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${tok}`, "Content-Type": "application/json" },
    body: JSON.stringify({ recipient, message: { text } }),
  });
  return r.ok ? null : `${r.status} ${(await r.text()).slice(0, 400)}`;
}

async function aiReply(text: string, list: Product[]): Promise<string | null> {
  const key = Deno.env.get("ANTHROPIC_API_KEY");
  if (!key || (await setting("ai_dm_replies")) !== "on" || !text.trim()) return null;
  const facts = list.map((p) => `${p.name} (DM ${p.keyword}): ${p.pitch ?? ""} ${p.link}`).join("\n");
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({
      model: Deno.env.get("IRUN_MODEL") ?? "claude-haiku-5-5", max_tokens: 300,
      system: "You answer Instagram DMs for HSW365 Media (Hoodstar365). Reply in 1-3 short sentences, friendly and direct. " +
        "Use ONLY these products and links; never invent prices, features, discounts or promises. If the question is not about " +
        "them or you are unsure, say Hoodstar365 will reply personally soon. No emojis.\n\nPRODUCTS:\n" + facts,
      messages: [{ role: "user", content: text.slice(0, 1000) }],
    }),
  });
  if (!r.ok) return null;
  const j = await r.json();
  const out = (j.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("").trim();
  return out ? out.slice(0, 900) : null;
}

async function handle(body: any) {
  const list = await products();
  for (const entry of body.entry ?? []) {
    const me = String(entry.id ?? "");
    for (const ch of entry.changes ?? []) {
      if (ch.field !== "comments") continue;
      const v = ch.value ?? {};
      const uid = String(v.from?.id ?? "");
      if (!uid || uid === me) continue;
      const p = match(v.text ?? "", list);
      const row: any = { source: "comment", ig_user_id: uid, username: v.from?.username, message: v.text,
        keyword: p?.keyword ?? null, product_id: p?.id ?? null };
      if (p && !(await recentlySent(uid, p.id))) {
        const err = await send({ comment_id: String(v.id) }, replyText(p, v.from?.username));
        row.replied = !err; row.reply_error = err;
      }
      if (p) await sb.from("irun_leads").insert(row);
    }
    for (const m of entry.messaging ?? []) {
      const uid = String(m.sender?.id ?? "");
      const msg = m.message;
      if (!msg || msg.is_echo || !uid || uid === me) continue;
      const p = match(msg.text ?? "", list);
      const row: any = { source: "dm", ig_user_id: uid, message: msg.text ?? "[attachment]",
        keyword: p?.keyword ?? null, product_id: p?.id ?? null };
      if (p && !(await recentlySent(uid, p.id))) {
        const err = await send({ id: uid }, replyText(p));
        row.replied = !err; row.reply_error = err;
      } else if (!p) {
        const ai = await aiReply(msg.text ?? "", list).catch(() => null);
        if (ai) {
          const err = await send({ id: uid }, ai);
          row.replied = !err; row.reply_error = err ?? "ai reply";
        }
      }
      await sb.from("irun_leads").insert(row); // every inbound DM is logged, keyword or not
    }
  }
}

async function ownerData(key: string | null) {
  const owner = await setting("owner_key");
  if (!owner || key !== owner) return json({ error: "unauthorized" }, 401);
  const [posts, leads, prods] = await Promise.all([
    sb.from("irun_posts").select("id,created_at,platform,product_id,hook,caption,video_url,status,error,posted_at,voice")
      .order("created_at", { ascending: false }).limit(60),
    sb.from("irun_leads").select("*").order("created_at", { ascending: false }).limit(300),
    sb.from("irun_products").select("*"),
  ]);
  const tokens = await sb.from("irun_tokens").select("name,expires_at,updated_at");
  const [cos, acts] = await Promise.all([
    sb.from("irun_companies").select("id,name,email,source_url,handles,status,plan,credits,bonus_credits,credits_used_total,site_status,site_url,site_draft_url,outreach_enabled,last_review_at,last_report,error,client_key,created_at,profile")
      .order("created_at", { ascending: false }),
    sb.from("irun_activity").select("company_id,agent,action,detail,created_at").order("created_at", { ascending: false }).limit(200),
  ]);
  const settings = await sb.from("irun_settings").select("key,value").in("key", ["billing_live", "ai_dm_replies"]);
  return json({ posts: posts.data ?? [], leads: leads.data ?? [], products: prods.data ?? [], connections: tokens.data ?? [],
    companies: (cos.data ?? []).map((c: any) => ({ ...c, offers: (c.profile?.products ?? []).map((p: any) => p.name), profile: undefined })),
    activity: acts.data ?? [], settings: Object.fromEntries((settings.data ?? []).map((r: any) => [r.key, r.value])) });
}

const slug = (s: string) => (s.toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 32) || "company");
const emailOk = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);
const RESERVED = ["hsw365media", "hoodstar365", "hsw365co", "newark"];

async function ownerAction(b: any) {
  const owner = await setting("owner_key");
  if (!owner || b.owner !== owner) return json({ error: "unauthorized" }, 401);
  const log = (company_id: string | null, action: string) => sb.from("irun_activity").insert({ company_id, agent: "owner", action });
  if (b.a === "add_company") {
    const name = String(b.name ?? "").trim().slice(0, 80);
    if (name.length < 2) return json({ error: "Business name is required." }, 400);
    let id = slug(name);
    for (let n = 2; ; n++) {
      const { data } = await sb.from("irun_companies").select("id").eq("id", id).maybeSingle();
      if (!data && !RESERVED.includes(id)) break;
      id = slug(name) + n;
    }
    const handles: Record<string, string> = {};
    for (const k of ["instagram", "tiktok", "youtube"]) {
      const v = String(b.handles?.[k] ?? "").trim().replace(/^@/, "").replace(/[^A-Za-z0-9._]/g, "");
      if (v) handles[k] = v;
    }
    const email = String(b.email ?? "").trim().toLowerCase();
    const { error } = await sb.from("irun_companies").insert({ id, name, source_url: String(b.url ?? "").trim() || null, handles,
      notes: String(b.notes ?? "").trim() || null, email: emailOk(email) ? email : null, plan: "comp", status: "pending" });
    if (error) return json({ error: error.message }, 500);
    await log(id, `company added: ${name}. Onboarding starts within the hour.`);
    return json({ id });
  }
  const { data: c } = await sb.from("irun_companies").select("*").eq("id", String(b.id ?? "")).maybeSingle();
  if (!c) return json({ error: "no such company" }, 404);
  if (b.a === "company") {
    const up: Record<string, unknown> = { updated_at: new Date().toISOString() };
    if (["active", "paused", "pending"].includes(b.status)) up.status = b.status;
    if (typeof b.outreach_enabled === "boolean") up.outreach_enabled = b.outreach_enabled;
    if (b.approve_site && c.site_status === "draft") up.site_status = "approved";
    if (b.rebuild_site) up.site_status = "none";
    if (b.plan && ["comp", "starter", "pro", "elite"].includes(b.plan)) up.plan = b.plan;
    await sb.from("irun_companies").update(up).eq("id", c.id);
    await log(c.id, `owner update: ${Object.keys(up).filter((k) => k !== "updated_at").join(", ")}`);
    return json({ ok: true });
  }
  if (b.a === "credits") {
    const n = Math.floor(Number(b.n));
    if (!n || Math.abs(n) > 10000) return json({ error: "bad amount" }, 400);
    await sb.from("irun_companies").update({ bonus_credits: Math.max(0, c.bonus_credits + n) }).eq("id", c.id);
    await sb.from("irun_credit_ledger").insert({ company_id: c.id, delta: n, reason: "owner adjustment" });
    await log(c.id, `owner ${n > 0 ? "added" : "removed"} ${Math.abs(n)} credits`);
    return json({ ok: true });
  }
  if (b.a === "prospects") {
    const rows = (Array.isArray(b.rows) ? b.rows : []).slice(0, 2000)
      .map((r: any) => ({ company_id: c.id, email: String(r.email ?? "").trim().toLowerCase(), name: r.name || null, business: r.business || null, note: r.note || null }))
      .filter((r: any) => emailOk(r.email));
    if (!rows.length) return json({ error: "No valid emails found." }, 400);
    const { error } = await sb.from("irun_prospects").upsert(rows, { onConflict: "company_id,email", ignoreDuplicates: true });
    if (error) return json({ error: error.message }, 500);
    await log(c.id, `${rows.length} prospects added`);
    return json({ added: rows.length });
  }
  return json({ error: "unknown action" }, 400);
}

async function unsubscribe(url: URL) {
  const c = url.searchParams.get("c") ?? "", e = (url.searchParams.get("e") ?? "").toLowerCase(), t = url.searchParams.get("t") ?? "";
  const secret = await setting("unsub_secret");
  let ok = false;
  if (secret && c && e && t) {
    const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const mac = new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(`${c}|${e}`)));
    ok = Array.from(mac).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32) === t;
  }
  if (ok) {
    await sb.from("irun_suppress").upsert({ email: e, reason: `unsubscribed (${c})` });
    await sb.from("irun_prospects").update({ status: "unsubscribed" }).eq("email", e);
    await sb.from("irun_activity").insert({ company_id: c, agent: "outreach", action: `${e} unsubscribed` });
  }
  const msg = ok ? "You're unsubscribed. You won't get any more emails from us." : "This unsubscribe link is not valid.";
  return new Response(`<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>Unsubscribe</title>` +
    `<body style="font:16px/1.5 system-ui;background:#0a0a0f;color:#f2f2f7;display:grid;place-items:center;min-height:90vh;margin:0;padding:16px">` +
    `<p style="max-width:32ch;text-align:center">${msg}</p>`, { status: ok ? 200 : 400, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  if (req.method === "GET") {
    if (url.searchParams.get("hub.mode") === "subscribe") {
      const ok = url.searchParams.get("hub.verify_token") === (await setting("ig_verify_token"));
      return ok ? new Response(url.searchParams.get("hub.challenge") ?? "", { status: 200 }) : new Response("forbidden", { status: 403 });
    }
    if (url.searchParams.get("view") === "data") return ownerData(url.searchParams.get("key"));
    if (url.searchParams.get("view") === "unsub") return unsubscribe(url);
    return json({ ok: true, service: "irun-ig-webhook" });
  }
  if (req.method === "POST") {
    if (url.searchParams.get("view") === "unsub") return unsubscribe(url); // List-Unsubscribe-Post one-click
    const raw = await req.text();
    if (raw.startsWith("{") && raw.includes('"owner"')) {
      let b: any = null;
      try { b = JSON.parse(raw); } catch { /* not JSON: fall through to Meta */ }
      if (b?.owner) {
        try { return await ownerAction(b); } catch (e) { return json({ error: String(e instanceof Error ? e.message : e) }, 500); }
      }
    }
    if (!(await validSignature(req, raw))) return new Response("bad signature", { status: 401 });
    try { await handle(JSON.parse(raw)); } catch (e) { console.error("irun webhook error", e); }
    return new Response("EVENT_RECEIVED", { status: 200 }); // always 200 so Meta doesn't disable the webhook
  }
  return new Response("method not allowed", { status: 405 });
});
