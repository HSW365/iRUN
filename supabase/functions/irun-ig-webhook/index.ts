// iRun Instagram lead bot + owner data API.
// - GET  ?hub.mode=subscribe&hub.verify_token=..&hub.challenge=..  -> Meta webhook verification
// - POST (Meta webhook): comment "KEYWORD" -> private-reply DM with the link; DM "KEYWORD" -> reply with link. Every lead logged.
// - GET  ?view=data&key=OWNER_KEY -> JSON for the owner dashboard (dashboard.html)
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
  return json({ posts: posts.data ?? [], leads: leads.data ?? [], products: prods.data ?? [], connections: tokens.data ?? [] });
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
    return json({ ok: true, service: "irun-ig-webhook" });
  }
  if (req.method === "POST") {
    const raw = await req.text();
    if (!(await validSignature(req, raw))) return new Response("bad signature", { status: 401 });
    try { await handle(JSON.parse(raw)); } catch (e) { console.error("irun webhook error", e); }
    return new Response("EVENT_RECEIVED", { status: 200 }); // always 200 so Meta doesn't disable the webhook
  }
  return new Response("method not allowed", { status: 405 });
});
