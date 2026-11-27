// HSW365 Army owner API. Every call needs a valid owner PIN token (same one as the owner-pin function).
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });
const enc = new TextEncoder();
const b64u = (u: Uint8Array) => btoa(String.fromCharCode(...u)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function owner(token: string) {
  const [exp, sig] = token.split(".");
  if (!exp || !sig || !(Number(exp) > Date.now())) return false;
  const { data } = await db.from("owner_pin").select("token_secret").eq("id", 1).single();
  if (!data?.token_secret) return false;
  const k = await crypto.subtle.importKey("raw", enc.encode(data.token_secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const good = b64u(new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(exp))));
  if (good.length !== sig.length) return false;
  let d = 0;
  for (let i = 0; i < good.length; i++) d |= good.charCodeAt(i) ^ sig.charCodeAt(i);
  return d === 0;
}

const count = async (kind: string, status: string) =>
  (await db.from("army_leads").select("email", { count: "exact", head: true }).eq("kind", kind).eq("status", status)).count ?? 0;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const b = await req.json().catch(() => ({}));
    if (!(await owner(String(b.token ?? "")))) return json({ ok: false, error: "Owner sign-in required." }, 401);
    if (b.a === "overview") {
      const [agents, bn, cn, bs, cs] = await Promise.all([
        db.from("army_agents").select("*").order("id"),
        count("booking", "new"), count("customer", "new"), count("booking", "contacted"), count("customer", "contacted"),
      ]);
      if (agents.error) throw agents.error;
      return json({ ok: true, agents: agents.data, counts: { booking: bn, customer: cn, contacted: bs + cs } });
    }
    if (b.a === "leads") {
      const kind = b.kind === "customer" ? "customer" : "booking";
      let q = db.from("army_leads").select("*").eq("kind", kind).eq("status", "new")
        .order("priority").order("found_at", { ascending: false }).limit(50);
      if (/^[A-Z]{2}$/.test(b.state ?? "")) q = q.eq("state", b.state);
      const { data, error } = await q;
      if (error) throw error;
      return json({ ok: true, leads: data });
    }
    if (b.a === "mark") {
      const status = ["contacted", "skipped", "replied", "new"].includes(b.status) ? b.status : null;
      const emails = Array.isArray(b.emails) ? b.emails.slice(0, 50).map(String) : [];
      if (!status || !emails.length) return json({ ok: false, error: "Nothing to update." }, 400);
      const { error } = await db.from("army_leads").update({ status, updated_at: new Date().toISOString() }).in("email", emails);
      if (error) throw error;
      return json({ ok: true });
    }
    return json({ ok: false, error: "Unknown action." }, 400);
  } catch (e) {
    console.error(e);
    return json({ ok: false, error: "Server error." }, 500);
  }
});
