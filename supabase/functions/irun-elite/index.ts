// HSW365 Elite website orders.
//   POST {a:"submit", name, email, phone, order_ref, business, domain_have, domain_want, socials:{}, about, services, area, style, links, notes}
//        -> {id, key}   (customer intake after purchase; the build engine picks it up)
//   POST {a:"view", id, key}              -> status, version, demo_html for the customer's review page
//   POST {a:"approve", id, key}           -> marks the demo approved
//   POST {a:"revise", id, key, notes}     -> asks for changes; the engine rebuilds the demo from the notes
// JWT verification is off: customers call this from a static page. Every customer action needs the order's own key.
// A submit that carries a verified owner PIN session (owner_token) is the owner's own build: no deposit, marked OWNER VIP.
import { createClient } from "jsr:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-hsw-owner",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
// HSW365 owner PIN session (owner-login.js). The browser sends the signed token as header X-HSW-Owner or body
// field owner_token; it is re-checked with the owner-pin service and a positive answer is cached for 5 minutes.
const OWNER_PIN_URL = "https://lsxdlmrjrcivxwgfkpop.supabase.co/functions/v1/owner-pin";
const ownerSeen = new Map<string, number>();
async function ownerPin(req: Request, b?: Record<string, unknown> | null): Promise<boolean> {
  const t = String(req.headers.get("x-hsw-owner") || (b && b.owner_token) || "").trim();
  if (!t || t.length > 512) return false;
  const exp = ownerSeen.get(t);
  if (exp && exp > Date.now()) return true;
  try {
    const r = await fetch(OWNER_PIN_URL, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ a: "verify", token: t }), signal: AbortSignal.timeout(8000),
    });
    const j = await r.json().catch(() => null);
    if (j?.ok === true) { ownerSeen.set(t, Date.now() + 300_000); return true; }
  } catch (_) { /* owner-pin unreachable: not verified */ }
  ownerSeen.delete(t);
  return false;
}
const s = (v: unknown, n = 600) => String(v ?? "").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "").trim().slice(0, n);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  let b: Record<string, any>;
  try { b = await req.json(); } catch { return json({ error: "Bad request" }, 400); }

  if (b.a === "submit") {
    if (s(b.website_hp)) return json({ ok: true });                       // honeypot
    const pin = await ownerPin(req, b);
    const name = s(b.name, 120), email = s(b.email, 200).toLowerCase(), business = s(b.business, 160);
    if (!name || !business || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json({ error: "Name, business name and a valid email are required." }, 400);
    const since = new Date(Date.now() - 3600_000).toISOString();
    const { count } = await db.from("irun_elite_orders").select("id", { count: "exact", head: true }).eq("email", email).gte("created_at", since);
    if ((count ?? 0) >= 5 && !pin) return json({ error: "Too many submissions. Email hsw365media@gmail.com." }, 429);
    const socials: Record<string, string> = {};
    for (const k of ["instagram", "facebook", "tiktok", "youtube", "x", "linkedin", "other"]) {
      const v = s(b.socials?.[k], 120); if (v) socials[k] = v;
    }
    const intake = {
      domain_have: s(b.domain_have, 200), domain_want: s(b.domain_want, 300), socials,
      about: s(b.about, 2500), services: s(b.services, 2000), area: s(b.area, 300), style: s(b.style, 600),
      links: s(b.links, 800), notes: s(b.notes, 2000),
    };
    const { data, error } = await db.from("irun_elite_orders")
      .insert({ name, email, phone: s(b.phone, 40), order_ref: pin ? "OWNER VIP (no charge)" : s(b.order_ref, 60), business, intake })
      .select("id,key").single();
    if (error) return json({ error: "Could not save. Try again." }, 500);
    return json({ ok: true, id: data.id, key: data.key });
  }

  const id = s(b.id, 60), key = s(b.key, 60);
  const { data: o } = await db.from("irun_elite_orders").select("*").eq("id", id).eq("key", key).maybeSingle();
  if (!o) return json({ error: "Order not found." }, 404);

  if (b.a === "view") {
    return json({ ok: true, status: o.status, version: o.version, business: o.business, name: o.name,
      demo_html: o.status === "demo_ready" || o.status === "approved" ? o.demo_html : null,
      revision_notes: o.revision_notes });
  }
  if (b.a === "approve") {
    if (!o.demo_html) return json({ error: "No demo to approve yet." }, 400);
    const hist = [...(o.history ?? []), { at: new Date().toISOString(), event: "approved", version: o.version }];
    await db.from("irun_elite_orders").update({ status: "approved", history: hist, updated_at: new Date().toISOString() }).eq("id", id);
    return json({ ok: true });
  }
  if (b.a === "revise") {
    const notes = s(b.notes, 3000);
    if (notes.length < 5) return json({ error: "Tell us what to change." }, 400);
    const hist = [...(o.history ?? []), { at: new Date().toISOString(), event: "revision", version: o.version, notes }];
    await db.from("irun_elite_orders").update({ status: "revision", revision_notes: notes, history: hist, updated_at: new Date().toISOString() }).eq("id", id);
    return json({ ok: true });
  }
  return json({ error: "Unknown action" }, 400);
});
