// iRun growth API.
// - POST ?shop=ACCOUNT  Shopify "Order creation" webhook. Verified with that store's webhook signing secret
//                       (irun_settings key "shopify_webhook_secret:ACCOUNT"). Logs the order, then pings
//                       irun_settings "notify_url" if set (any URL that accepts a plain-text POST, e.g. an ntfy.sh topic).
// - GET  ?view=growth&key=OWNER_KEY  orders + measured posts for dashboard.html
// No customer names, emails or addresses are stored: only the order number, total, items and where the visit came from.
import { createClient } from "npm:@supabase/supabase-js@2";

const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
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

function same(a: string, b: string) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function hmacBase64(secret: string, raw: string) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(raw)));
  return btoa(String.fromCharCode(...mac));
}

async function notify(text: string) {
  const url = await setting("notify_url");
  if (!url || !/^https:\/\//.test(url)) return;
  try {
    await fetch(url, { method: "POST", headers: { "Content-Type": "text/plain", Title: "iRun: new order" }, body: text });
  } catch (e) {
    console.error("irun notify failed", e);
  }
}

async function order(req: Request, account: string) {
  const raw = await req.text();
  const secret = await setting(`shopify_webhook_secret:${account}`);
  if (!secret) return new Response("store not set up", { status: 401 });
  const sig = req.headers.get("x-shopify-hmac-sha256") || "";
  if (!same(sig, await hmacBase64(secret, raw))) return new Response("bad signature", { status: 401 });
  let o: any;
  try { o = JSON.parse(raw); } catch { return new Response("bad body", { status: 400 }); }
  if (!o?.id) return new Response("ok", { status: 200 });
  const items = (o.line_items ?? []).map((i: any) => ({ title: i.title, quantity: i.quantity, price: i.price }));
  const row = {
    account,
    shop_domain: req.headers.get("x-shopify-shop-domain"),
    order_id: String(o.id),
    name: o.name ?? null,
    total: o.total_price != null ? Number(o.total_price) : null,
    currency: o.currency ?? null,
    item_count: items.reduce((n: number, i: any) => n + (Number(i.quantity) || 0), 0),
    items,
    landing_site: o.landing_site ? String(o.landing_site).slice(0, 500) : null,
    referring_site: o.referring_site ? String(o.referring_site).slice(0, 500) : null,
    placed_at: o.created_at ?? null,
  };
  const { data, error } = await sb.from("irun_orders")
    .upsert(row, { onConflict: "account,order_id", ignoreDuplicates: true }).select("id");
  if (error) { console.error("irun order insert failed", error); return new Response("error", { status: 500 }); }
  if ((data ?? []).length) { // Shopify retries deliveries; only announce an order the first time
    const list = items.map((i: any) => `${i.quantity} x ${i.title}`).join(", ");
    await notify(`${row.name ?? "Order"} on ${account}: ${row.total ?? "?"} ${row.currency ?? ""} - ${list}`.trim());
  }
  return new Response("ok", { status: 200 });
}

async function growth(key: string | null) {
  const owner = await setting("owner_key");
  if (!owner || !key || !same(key, owner)) return json({ error: "unauthorized" }, 401);
  const [orders, posts] = await Promise.all([
    sb.from("irun_orders").select("*").order("created_at", { ascending: false }).limit(200),
    sb.from("irun_posts")
      .select("id,created_at,account,platform,product_id,angle,format,experiment,variant,hook,video_url,media,status,posted_at,metrics,score")
      .order("created_at", { ascending: false }).limit(200),
  ]);
  return json({ orders: orders.data ?? [], posts: posts.data ?? [] });
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  if (req.method === "GET") {
    if (url.searchParams.get("view") === "growth") return growth(url.searchParams.get("key"));
    return json({ ok: true, service: "irun-growth" });
  }
  if (req.method === "POST") {
    const account = url.searchParams.get("shop") || "";
    if (!/^[a-z0-9_-]{1,40}$/.test(account)) return new Response("unknown store", { status: 400 });
    return order(req, account);
  }
  return new Response("method not allowed", { status: 405 });
});
