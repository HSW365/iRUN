// iRun Operator: customer API + Stripe billing.
//   POST {a:"plans"}                                        -> plans, credit price, whether sign-up is open
//   POST {a:"checkout", plan, name, email, url, handles, notes[, owner_key]}  -> Stripe Checkout URL (subscription)
//   POST {a:"claim", c, s}                                  -> client key for a paid checkout session
//   POST {a:"view", c, k}                                   -> the customer's live view of their company
//   POST {a:"credits", c, k, qty}                           -> Stripe Checkout URL for a credit pack
//   POST {a:"portal", c, k}                                 -> Stripe billing portal URL
//   POST {a:"prospects", c, k, rows:[{email,name,business,note}]}  -> add to the outreach list
//   POST {a:"settings", c, k, outreach_enabled?, approve_site?, rebuild_site?}
//   POST {a:"zelle_signup", plan, name, email, url, handles, notes}  -> company + Zelle payment instructions
//   POST {a:"zelle_pay", c, k, kind:"plan"|"credits", qty?}  -> Zelle payment instructions (renewal or credit pack)
//   POST {a:"shop_check", url}                             -> Shopify store preview (Shop Team page)
//   POST {a:"zelle_sent", c, k, id, note?}                 -> customer says the Zelle payment is sent; owner confirms it
//   POST {a:"fund_view", c, k}                              -> Fundraise: campaign, deck review, investor matches
//   POST {a:"fund_save", c, k, ...campaign fields, review?}  -> Fundraise: save the raise (+ request a deck review)
//   POST {a:"fund_import", c, k, rows:[investor...]}          -> Fundraise: add investors to match
//   POST {a:"fund_match", c, k, id, op, ...}                  -> Fundraise: approve | pass | restore | edit | meeting
//   POST with stripe-signature                              -> Stripe webhook
// JWT verification is off: Stripe calls this directly; customer actions check the company's client key.
// Plans live in irun_settings.plans (synced from config/plans.json). Sign-up opens when irun_settings.billing_live = on.
import { createClient } from "jsr:@supabase/supabase-js@2";

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const STRIPE = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const db = createClient(SB_URL, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const SITE = "https://hsw365.github.io/iRUN/";
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });

type Plan = { name: string; cents: number; credits: number; features: string[]; outreach: boolean; outreach_daily_cap: number };
type Plans = { credit_price_cents: number; credit_pack_min: number; credit_pack_max: number; plans: Record<string, Plan> };

async function setting(key: string) {
  const { data } = await db.from("irun_settings").select("value").eq("key", key).maybeSingle();
  return data?.value ?? null;
}
async function plans(): Promise<Plans> {
  return JSON.parse((await setting("plans")) ?? "{}");
}
async function stripe(path: string, params?: Record<string, string>) {
  const r = await fetch("https://api.stripe.com/v1/" + path, {
    method: params ? "POST" : "GET",
    headers: { Authorization: "Bearer " + STRIPE, "Content-Type": "application/x-www-form-urlencoded" },
    body: params ? new URLSearchParams(params).toString() : undefined,
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j?.error?.message ?? "Stripe request failed");
  return j;
}
async function ensureWebhook() {
  if (await setting("stripe_whsec")) return;
  const w = await stripe("webhook_endpoints", {
    url: SB_URL + "/functions/v1/irun-client",
    "enabled_events[0]": "checkout.session.completed",
    "enabled_events[1]": "invoice.paid",
    "enabled_events[2]": "customer.subscription.deleted",
    description: "iRun Operator subscriptions and credits",
  });
  await db.from("irun_settings").upsert({ key: "stripe_whsec", value: w.secret });
}
const hex = (buf: ArrayBuffer) => Array.from(new Uint8Array(buf)).map((x) => x.toString(16).padStart(2, "0")).join("");
async function verifySig(body: string, header: string, secret: string) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=") as [string, string]));
  const t = Number(parts.t);
  if (!t || Math.abs(Date.now() / 1000 - t) > 300) return false;
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const want = hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(t + "." + body)));
  return header.split(",").filter((p) => p.startsWith("v1=")).some((p) => p.slice(3) === want);
}
const days = (n: number) => new Date(Date.now() + n * 86400_000).toISOString();
const slug = (s: string) => (s.toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 32) || "company");
const emailOk = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);

async function zelle() {
  const [phone, email, name] = await Promise.all([setting("zelle_phone"), setting("zelle_email"), setting("zelle_name")]);
  return phone || email ? { phone, email, name } : null;
}
// A Zelle payment the owner confirms in the dashboard. The memo code ties the transfer to the company.
async function zellePayment(c: { id: string }, kind: "plan" | "credits", planId: string | null, qty: number | null, cents: number) {
  const ref = `IRUN-${c.id.slice(0, 10).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
  const { data } = await db.from("irun_payments").insert({ company_id: c.id, kind, plan: planId, qty, amount_cents: cents, ref })
    .select("id,kind,plan,qty,amount_cents,ref,status,created_at").single();
  await log(c.id, "billing", `Zelle payment requested: $${(cents / 100).toFixed(2)} (${kind === "plan" ? planId + " plan" : qty + " credits"}), memo ${ref}`);
  return data;
}
// Owner emails (irun_settings.owner_emails, synced from config/owners.json) get every plan free, forever.
async function isOwner(email: string) {
  const list = JSON.parse((await setting("owner_emails")) ?? "[]") as string[];
  return list.map((e) => e.toLowerCase()).includes(email.trim().toLowerCase());
}
async function newCompany(b: any, pl: Plans, payMethod: string) {
  const plan = pl.plans[b.plan];
  const name = String(b.name ?? "").trim().slice(0, 80);
  const email = String(b.email ?? "").trim().toLowerCase();
  const url = String(b.url ?? "").trim().slice(0, 300);
  if (!plan) throw new Error("Pick a plan.");
  if (name.length < 2) throw new Error("Enter your business name.");
  if (!emailOk(email)) throw new Error("Enter a valid email.");
  if (!url && !String(b.notes ?? "").trim()) throw new Error("Add your website, or tell us about your business.");
  const handles: Record<string, string> = {};
  for (const k of ["instagram", "tiktok", "youtube"]) {
    const v = String(b.handles?.[k] ?? "").trim().replace(/^@/, "").replace(/[^A-Za-z0-9._]/g, "").slice(0, 40);
    if (v) handles[k] = v;
  }
  let id = slug(name);
  for (let n = 2; ; n++) {
    const { data } = await db.from("irun_companies").select("id").eq("id", id).maybeSingle();
    if (!data && !["hsw365media", "hoodstar365", "hsw365co", "newark"].includes(id)) break;
    id = slug(name) + n;
  }
  const owner = await isOwner(email);
  const { data, error } = await db.from("irun_companies").insert({ id, name, email, source_url: url || null, handles,
    notes: String(b.notes ?? "").slice(0, 2000) || null, plan: owner ? "comp" : b.plan,
    status: owner ? "pending" : "awaiting_payment", pay_method: owner ? "comp" : payMethod })
    .select("id,client_key").single();
  if (error) throw new Error(error.message);
  if (owner) await log(id, "billing", "owner account: full access, no charge. Onboarding starts within the hour.");
  return { ...data, plan, planId: b.plan as string, owner };
}

async function company(c: string, k: string) {
  if (!c || !k) return null;
  const { data } = await db.from("irun_companies").select("*").eq("id", c).maybeSingle();
  if (!data || data.client_key !== k) return null;
  return data;
}
async function log(company_id: string, agent: string, action: string, detail: unknown = null) {
  await db.from("irun_activity").insert({ company_id, agent, action, detail });
}
async function seen(ref: string) {
  const { data } = await db.from("irun_credit_ledger").select("id").eq("ref", ref).limit(1);
  return (data ?? []).length > 0;
}

// A paid plan checkout: switch the company on and load its first month of credits (idempotent per session).
async function activate(session: any) {
  const cid = session.metadata?.company_id;
  const planId = session.metadata?.plan;
  if (!cid || !planId || (await seen(session.id))) return;
  const p = (await plans()).plans[planId];
  if (!p) return;
  const { data: c } = await db.from("irun_companies").select("status").eq("id", cid).maybeSingle();
  if (!c) return;
  await db.from("irun_companies").update({
    plan: planId, credits: p.credits, stripe_customer: session.customer, stripe_sub: session.subscription,
    paid_until: days(3), status: c.status === "awaiting_payment" || c.status === "paused" ? "pending" : c.status,
    updated_at: new Date().toISOString(),
  }).eq("id", cid);
  await db.from("irun_credit_ledger").insert({ company_id: cid, delta: p.credits, reason: `${p.name} plan: first month`, ref: session.id });
  await log(cid, "billing", `${p.name} plan active: ${p.credits} credits loaded. Onboarding starts within the hour.`);
}
async function addCredits(session: any) {
  const cid = session.metadata?.company_id;
  const qty = Number(session.metadata?.qty);
  if (!cid || !qty || (await seen(session.id))) return;
  const { data: c } = await db.from("irun_companies").select("bonus_credits").eq("id", cid).maybeSingle();
  if (!c) return;
  await db.from("irun_companies").update({ bonus_credits: c.bonus_credits + qty, updated_at: new Date().toISOString() }).eq("id", cid);
  await db.from("irun_credit_ledger").insert({ company_id: cid, delta: qty, reason: `bought ${qty} credits`, ref: session.id });
  await log(cid, "billing", `${qty} credits added`);
}

async function webhook(req: Request) {
  const body = await req.text();
  const secret = await setting("stripe_whsec");
  if (!secret || !(await verifySig(body, req.headers.get("stripe-signature")!, secret))) return json({ error: "Bad signature" }, 400);
  const ev = JSON.parse(body);
  const o = ev.data?.object ?? {};
  if (ev.type === "checkout.session.completed" && o.metadata?.app === "irun" && ["paid", "no_payment_required"].includes(o.payment_status)) {
    if (o.metadata.kind === "plan") await activate(o);
    if (o.metadata.kind === "credits") await addCredits(o);
  }
  if (ev.type === "invoice.paid" && o.billing_reason === "subscription_cycle" && !(await seen(o.id))) {
    const sub = o.subscription ?? o.parent?.subscription_details?.subscription;
    const { data: c } = await db.from("irun_companies").select("id,plan,status").eq("stripe_sub", sub).maybeSingle();
    const p = c && (await plans()).plans[c.plan];
    if (c && p) {
      const end = o.lines?.data?.[0]?.period?.end;
      await db.from("irun_companies").update({
        credits: p.credits, paid_until: end ? new Date((end + 2 * 86400) * 1000).toISOString() : days(33),
        status: c.status === "paused" ? "active" : c.status, updated_at: new Date().toISOString(),
      }).eq("id", c.id);
      await db.from("irun_credit_ledger").insert({ company_id: c.id, delta: p.credits, reason: `${p.name} plan: monthly refill`, ref: o.id });
      await log(c.id, "billing", `new month: plan credits refilled to ${p.credits}`);
    }
  }
  if (ev.type === "customer.subscription.deleted" && o.id) {
    const { data: c } = await db.from("irun_companies").select("id").eq("stripe_sub", o.id).maybeSingle();
    if (c) {
      await db.from("irun_companies").update({ status: "paused", stripe_sub: null, credits: 0, updated_at: new Date().toISOString() }).eq("id", c.id);
      await log(c.id, "billing", "subscription ended: autopilot paused (purchased credits are kept)");
    }
  }
  return json({ received: true });
}

async function view(c: any) {
  const [acts, posts, ledger, pros, pays] = await Promise.all([
    db.from("irun_activity").select("agent,action,detail,created_at").eq("company_id", c.id).order("created_at", { ascending: false }).limit(120),
    db.from("irun_posts").select("platform,product_id,hook,caption,video_url,status,error,created_at,posted_at,format")
      .eq("account", c.id).order("created_at", { ascending: false }).limit(40),
    db.from("irun_credit_ledger").select("delta,reason,created_at").eq("company_id", c.id).order("created_at", { ascending: false }).limit(40),
    db.from("irun_prospects").select("status").eq("company_id", c.id),
    db.from("irun_payments").select("id,kind,plan,qty,amount_cents,ref,status,created_at").eq("company_id", c.id)
      .order("created_at", { ascending: false }).limit(10),
  ]);
  const counts: Record<string, number> = {};
  for (const p of pros.data ?? []) counts[p.status] = (counts[p.status] ?? 0) + 1;
  const pl = await plans();
  const prof = c.profile ?? {};
  return {
    company: {
      id: c.id, name: prof.brand ?? c.name, status: c.status, plan: c.plan, plan_name: pl.plans?.[c.plan]?.name ?? "Comp",
      credits: c.credits, bonus_credits: c.bonus_credits, paid_until: c.paid_until, summary: prof.summary ?? null,
      offers: (prof.products ?? []).map((p: any) => ({ name: p.name, angles: p.angles })),
      site_status: c.site_status, site_url: c.site_url, site_draft_url: c.site_draft_url,
      outreach_enabled: c.outreach_enabled, outreach_available: !!pl.plans?.[c.plan]?.outreach || c.plan === "comp",
      last_report: c.last_report, last_review_at: c.last_review_at, error: c.status === "error" ? c.error : null,
      handles: c.handles, fundraise: !!pl.plans?.[c.plan]?.fundraise || c.plan === "comp",
    },
    activity: acts.data ?? [], posts: posts.data ?? [], ledger: ledger.data ?? [], prospects: counts,
    credit_price_cents: pl.credit_price_cents, pack: [pl.credit_pack_min, pl.credit_pack_max],
    payments: pays.data ?? [], zelle: await zelle(), card: !!STRIPE, pay_method: c.pay_method,
  };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  try {
    if (req.headers.get("stripe-signature")) return await webhook(req);
    const b = await req.json().catch(() => ({}));
    const pl = await plans();

    if (b.a === "plans") {
      const z = await zelle();
      return json({ plans: pl.plans, credit_price_cents: pl.credit_price_cents, pack: [pl.credit_pack_min, pl.credit_pack_max],
        open: (await setting("billing_live")) === "on" && (!!STRIPE || !!z), card: !!STRIPE, zelle: z });
    }

    // Shop Team: preview a Shopify store's first products (public /products.json, read server-side: no CORS on it).
    if (b.a === "shop_check") {
      const d = String(b.url ?? "").trim().toLowerCase().replace(/^https?:\/\//, "").split(/[\/?#]/)[0].replace(/\.+$/, "");
      if (!/^[a-z0-9.-]+\.[a-z]{2,}$/.test(d)) return json({ shopify: false, error: "Enter your store link, like yourstore.com" });
      try {
        const r = await fetch(`https://${d}/products.json?limit=24`, { headers: { "User-Agent": "iRunShopTeam/1.0" },
          signal: AbortSignal.timeout(9000) });
        const j = r.ok ? await r.json().catch(() => null) : null;
        const rows = (j?.products ?? []).filter((x: any) => x.images?.length).slice(0, 6).map((x: any) => {
          const v = (x.variants ?? []).find((y: any) => y.available !== false) ?? x.variants?.[0] ?? {};
          return { title: String(x.title).slice(0, 80), price: Number(v.price ?? 0), image: x.images[0].src, vendor: x.vendor ?? "" };
        });
        return json({ shopify: !!j?.products, store: d, count: j?.products?.length ?? 0, products: rows });
      } catch (_) {
        return json({ shopify: false, store: d });
      }
    }

    if (b.a === "zelle_signup") {
      const z = await zelle();
      if ((await setting("billing_live")) !== "on" || !z) return json({ error: "Sign-up opens soon." }, 403);
      let nc;
      try { nc = await newCompany(b, pl, "zelle"); } catch (e) { return json({ error: (e as Error).message }, 400); }
      if (nc.owner) return json({ c: nc.id, k: nc.client_key });
      const pay = await zellePayment(nc, "plan", nc.planId, null, nc.plan.cents);
      return json({ c: nc.id, k: nc.client_key, payment: pay, zelle: z });
    }

    if (b.a === "checkout" && pl.plans[b.plan]?.cents === 0) {
      // Free plan (Shop Team): no payment. The company starts onboarding within the hour.
      let nc;
      try { nc = await newCompany(b, pl, "free"); } catch (e) { return json({ error: (e as Error).message }, 400); }
      if (!nc.owner) {
        await db.from("irun_companies").update({ status: "pending", credits: nc.plan.credits, paid_until: days(3650),
          updated_at: new Date().toISOString() }).eq("id", nc.id);
        await db.from("irun_credit_ledger").insert({ company_id: nc.id, delta: nc.plan.credits, reason: `${nc.plan.name}: free plan`, ref: `free-${nc.id}` });
        await log(nc.id, "billing", `${nc.plan.name} is free: ${nc.plan.credits} ads loaded. Onboarding starts within the hour.`);
      }
      return json({ c: nc.id, k: nc.client_key });
    }

    if (b.a === "checkout") {
      const owner = b.owner_key && b.owner_key === (await setting("owner_key"));
      if ((await setting("billing_live")) !== "on" && !owner) return json({ error: "Sign-up opens soon." }, 403);
      if (!STRIPE && !(await isOwner(String(b.email ?? "")))) return json({ error: "Payments are not configured yet." }, 503);
      let nc;
      try { nc = await newCompany(b, pl, "card"); } catch (e) { return json({ error: (e as Error).message }, 400); }
      if (nc.owner) return json({ c: nc.id, k: nc.client_key });
      const { id, plan } = nc;
      const email = String(b.email).trim().toLowerCase();
      await ensureWebhook();
      const s = await stripe("checkout/sessions", {
        mode: "subscription", customer_email: email, client_reference_id: id,
        "metadata[app]": "irun", "metadata[kind]": "plan", "metadata[plan]": b.plan, "metadata[company_id]": id,
        "subscription_data[metadata][app]": "irun", "subscription_data[metadata][company_id]": id,
        "subscription_data[trial_period_days]": "3",
        success_url: b.plan === "fundraise" ? `${SITE}raise.html?c=${id}&s={CHECKOUT_SESSION_ID}` : `${SITE}client.html?c=${id}&s={CHECKOUT_SESSION_ID}`,
        cancel_url: b.plan === "shopify" ? `${SITE}shopteam.html#start` : b.plan === "fundraise" ? `${SITE}fundraise.html#start` : `${SITE}start.html?plan=${b.plan}`,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": String(plan.cents),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][product_data][name]": `iRun ${plan.name}`,
      });
      await log(id, "billing", `checkout started for the ${plan.name} plan`);
      return json({ url: s.url });
    }

    if (b.a === "claim") {
      if (!STRIPE) return json({ error: "Payments are not configured yet." }, 503);
      const s = await stripe(`checkout/sessions/${encodeURIComponent(String(b.s ?? ""))}`);
      if (s.metadata?.app !== "irun" || s.metadata?.company_id !== b.c || !["paid", "no_payment_required"].includes(s.payment_status)) return json({ error: "Payment not found." }, 404);
      await activate(s); // in case the webhook has not landed yet
      const { data } = await db.from("irun_companies").select("client_key").eq("id", b.c).maybeSingle();
      return json({ k: data?.client_key });
    }

    const c = await company(String(b.c ?? ""), String(b.k ?? ""));
    if (!c) return json({ error: "This link is not valid." }, 401);

    if (b.a === "view") return json(await view(c));

    if (b.a === "zelle_pay") {
      const z = await zelle();
      if (!z) return json({ error: "Zelle is not set up." }, 503);
      if (b.kind === "credits") {
        const qty = Math.floor(Number(b.qty));
        if (!(qty >= pl.credit_pack_min && qty <= pl.credit_pack_max)) return json({ error: `Buy between ${pl.credit_pack_min} and ${pl.credit_pack_max} credits.` }, 400);
        return json({ payment: await zellePayment(c, "credits", null, qty, qty * pl.credit_price_cents), zelle: z });
      }
      const plan = pl.plans[c.plan];
      if (!plan) return json({ error: "No plan to renew." }, 400);
      const { data: open } = await db.from("irun_payments").select("id,kind,plan,qty,amount_cents,ref,status,created_at")
        .eq("company_id", c.id).eq("kind", "plan").in("status", ["pending", "sent"]).limit(1);
      if (open?.length) return json({ payment: open[0], zelle: z });
      return json({ payment: await zellePayment(c, "plan", c.plan, null, plan.cents), zelle: z });
    }

    if (b.a === "zelle_sent") {
      const { data: p } = await db.from("irun_payments").select("id,status,ref,amount_cents").eq("id", Number(b.id)).eq("company_id", c.id).maybeSingle();
      if (!p || p.status !== "pending") return json({ error: "Payment not found." }, 404);
      await db.from("irun_payments").update({ status: "sent", note: String(b.note ?? "").slice(0, 300) || null }).eq("id", p.id);
      await log(c.id, "billing", `customer says Zelle payment ${p.ref} ($${(p.amount_cents / 100).toFixed(2)}) is sent: waiting for confirmation`);
      return json({ ok: true });
    }

    if (b.a === "credits") {
      if (!STRIPE) return json({ error: "Payments are not configured yet." }, 503);
      const qty = Math.floor(Number(b.qty));
      if (!(qty >= pl.credit_pack_min && qty <= pl.credit_pack_max)) return json({ error: `Buy between ${pl.credit_pack_min} and ${pl.credit_pack_max} credits.` }, 400);
      await ensureWebhook();
      const p: Record<string, string> = {
        mode: "payment", client_reference_id: c.id,
        "metadata[app]": "irun", "metadata[kind]": "credits", "metadata[company_id]": c.id, "metadata[qty]": String(qty),
        success_url: `${SITE}client.html?c=${c.id}&k=${c.client_key}&bought=${qty}`,
        cancel_url: `${SITE}client.html?c=${c.id}&k=${c.client_key}`,
        "line_items[0][quantity]": String(qty),
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": String(pl.credit_price_cents),
        "line_items[0][price_data][product_data][name]": "iRun credit",
      };
      if (c.stripe_customer) p.customer = c.stripe_customer; else if (c.email) p.customer_email = c.email;
      return json({ url: (await stripe("checkout/sessions", p)).url });
    }

    if (b.a === "portal") {
      if (!c.stripe_customer) return json({ error: "No billing on file." }, 400);
      const s = await stripe("billing_portal/sessions", { customer: c.stripe_customer, return_url: `${SITE}client.html?c=${c.id}&k=${c.client_key}` });
      return json({ url: s.url });
    }

    if (b.a === "prospects") {
      const rows = (Array.isArray(b.rows) ? b.rows : []).slice(0, 2000)
        .map((r: any) => ({ company_id: c.id, email: String(r.email ?? "").trim().toLowerCase(), name: String(r.name ?? "").slice(0, 120) || null,
          business: String(r.business ?? "").slice(0, 160) || null, note: String(r.note ?? "").slice(0, 500) || null }))
        .filter((r: any) => emailOk(r.email));
      if (!rows.length) return json({ error: "No valid emails found." }, 400);
      const { error } = await db.from("irun_prospects").upsert(rows, { onConflict: "company_id,email", ignoreDuplicates: true });
      if (error) return json({ error: error.message }, 500);
      await log(c.id, "outreach", `${rows.length} prospects added to the outreach list`);
      return json({ added: rows.length });
    }

    if (b.a === "settings") {
      const up: Record<string, unknown> = { updated_at: new Date().toISOString() };
      if (typeof b.outreach_enabled === "boolean") up.outreach_enabled = b.outreach_enabled;
      if (b.approve_site && c.site_status === "draft") up.site_status = "approved";
      if (b.rebuild_site && ["draft", "published"].includes(c.site_status)) up.site_status = "none";
      await db.from("irun_companies").update(up).eq("id", c.id);
      if (up.site_status === "approved") await log(c.id, "site", "website approved by the owner: publishing within the hour");
      if (up.site_status === "none") await log(c.id, "site", "new website version requested");
      if ("outreach_enabled" in up) await log(c.id, "outreach", `outreach switched ${b.outreach_enabled ? "on" : "off"}`);
      return json({ ok: true });
    }
    // ---------- Fundraise ----------
    if (b.a?.startsWith("fund_")) {
      const hasFund = !!pl.plans?.[c.plan]?.fundraise || c.plan === "comp";
      if (!hasFund) return json({ error: "Fundraise is not part of this plan." }, 403);
      const arr = (v: unknown, max = 12) => (Array.isArray(v) ? v : String(v ?? "").split(/[,;|]/)).map((x) => String(x).trim().toLowerCase().slice(0, 40)).filter(Boolean).slice(0, max);
      const num = (v: unknown) => { const n = Math.round(Number(String(v ?? "").replace(/[^0-9.]/g, ""))); return Number.isFinite(n) && n > 0 ? n : null; };
      const STAGES = ["pre-seed", "seed", "series-a", "series-b", "growth"];
      const stageOf = (v: unknown) => { const t = String(v ?? "").toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, ""); return STAGES.includes(t) ? t : t.replace("-", "") === "preseed" ? "pre-seed" : t.replace("-", "") === "seriesa" ? "series-a" : t.replace("-", "") === "seriesb" ? "series-b" : null; };

      if (b.a === "fund_view") {
        const [camp, inv, ms] = await Promise.all([
          db.from("irun_fund_campaigns").select("*").eq("company_id", c.id).maybeSingle(),
          db.from("irun_investors").select("id", { count: "exact", head: true }).eq("company_id", c.id),
          db.from("irun_fund_matches").select("id,score,reasons,status,subject,body,sends,last_sent_at,replied_at,meeting_at,meeting_note,error,irun_investors(name,firm,role,type,email,location,stages,sectors,check_min,check_max,website,note)")
            .eq("company_id", c.id).order("score", { ascending: false }).limit(600),
        ]);
        const counts: Record<string, number> = {};
        for (const m of ms.data ?? []) counts[m.status] = (counts[m.status] ?? 0) + 1;
        const camp0 = camp.data ? { ...camp.data, deck_text: undefined, deck_chars: (camp.data.deck_text ?? "").length } : null;
        return json({ campaign: camp0, investors: inv.count ?? 0, matches: ms.data ?? [], counts, smtp_note: "Sending needs the engine switched to live.",
          company: { id: c.id, name: c.name, status: c.status, plan: c.plan, credits: c.credits, bonus_credits: c.bonus_credits } });
      }

      if (b.a === "fund_save") {
        const up: Record<string, unknown> = { company_id: c.id, updated_at: new Date().toISOString() };
        const t = (k: string, n: number) => { if (k in b) up[k] = String(b[k] ?? "").trim().slice(0, n) || null; };
        t("startup", 120); t("one_liner", 300); t("geo", 120); t("traction", 2000);
        if ("booking_url" in b) {
          const u = String(b.booking_url ?? "").trim().slice(0, 300);
          if (u && !/^https:\/\/[^\s]+$/i.test(u)) return json({ error: "Booking link must start with https://" }, 400);
          up.booking_url = u || null;
        }
        if ("stage" in b) up.stage = stageOf(b.stage);
        if ("raise_usd" in b) up.raise_usd = num(b.raise_usd);
        if ("check_usd" in b) up.check_usd = num(b.check_usd);
        if ("sectors" in b) up.sectors = arr(b.sectors);
        if ("deck_text" in b) up.deck_text = String(b.deck_text ?? "").slice(0, 80000) || null;
        if (typeof b.send_enabled === "boolean") up.send_enabled = b.send_enabled;
        if (b.review) {
          const { data: cur } = await db.from("irun_fund_campaigns").select("deck_text").eq("company_id", c.id).maybeSingle();
          const deck = String(up.deck_text ?? cur?.deck_text ?? "");
          if (deck.trim().length < 200) return json({ error: "Paste or upload your deck first (at least a few slides of text)." }, 400);
          up.review_status = "requested"; up.review_error = null;
        }
        const { error } = await db.from("irun_fund_campaigns").upsert(up, { onConflict: "company_id" });
        if (error) return json({ error: error.message }, 500);
        if (b.review) await log(c.id, "fundraise", "deck review requested: it runs within the hour (1 credit)");
        if (typeof b.send_enabled === "boolean") await log(c.id, "fundraise", `investor outreach switched ${b.send_enabled ? "on" : "off"}`);
        return json({ ok: true });
      }

      if (b.a === "fund_import") {
        const rows = (Array.isArray(b.rows) ? b.rows : []).slice(0, 2000).map((r: any) => {
          const email = String(r.email ?? "").trim().toLowerCase();
          const type = ["vc", "angel", "family_office", "accelerator", "corporate"].includes(String(r.type ?? "").toLowerCase().replace(/\s+/g, "_")) ? String(r.type).toLowerCase().replace(/\s+/g, "_") : "vc";
          return {
            company_id: c.id, name: String(r.name ?? "").trim().slice(0, 120), firm: String(r.firm ?? "").trim().slice(0, 160) || null,
            role: String(r.role ?? "").trim().slice(0, 120) || null, type, email: email && emailOk(email) ? email : null,
            location: String(r.location ?? "").trim().slice(0, 120) || null,
            stages: arr(r.stages).map((x) => stageOf(x)).filter(Boolean) as string[], sectors: arr(r.sectors),
            check_min: num(r.check_min), check_max: num(r.check_max), website: String(r.website ?? "").trim().slice(0, 200) || null,
            note: String(r.note ?? "").trim().slice(0, 500) || null,
          };
        }).filter((r: any) => r.name.length >= 2);
        if (!rows.length) return json({ error: "No investors found. Each line needs at least a name." }, 400);
        const withEmail = rows.filter((r: any) => r.email), noEmail = rows.filter((r: any) => !r.email);
        if (withEmail.length) {
          const { error } = await db.from("irun_investors").upsert(withEmail, { onConflict: "company_id,email", ignoreDuplicates: true });
          if (error) return json({ error: error.message }, 500);
        }
        if (noEmail.length) await db.from("irun_investors").insert(noEmail);
        await log(c.id, "fundraise", `${rows.length} investors added: matching runs within the hour`);
        return json({ added: rows.length });
      }

      if (b.a === "fund_match") {
        const id = Number(b.id);
        const { data: m } = await db.from("irun_fund_matches").select("id,status,subject,body").eq("id", id).eq("company_id", c.id).maybeSingle();
        const up: Record<string, unknown> = { updated_at: new Date().toISOString() };
        if (!m && b.op !== "approve_all") return json({ error: "Match not found." }, 404);
        if (b.op === "approve_all") {
          const min = Math.max(0, Math.min(100, Number(b.min ?? 70)));
          const { data: ds } = await db.from("irun_fund_matches").select("id").eq("company_id", c.id).eq("status", "drafted").gte("score", min);
          const ids = (ds ?? []).map((x: any) => x.id);
          if (ids.length) await db.from("irun_fund_matches").update({ status: "approved", updated_at: up.updated_at }).in("id", ids);
          await log(c.id, "fundraise", `${ids.length} investor emails approved (score ${min}+)`);
          return json({ approved: ids.length });
        }
        if (b.op === "approve") { if (m!.status !== "drafted") return json({ error: "Only drafted emails can be approved." }, 400); up.status = "approved"; }
        else if (b.op === "unapprove") { if (m!.status !== "approved") return json({ error: "Already sent or not approved." }, 400); up.status = "drafted"; }
        else if (b.op === "pass") { if (["sent", "followed_up"].includes(m!.status)) return json({ error: "Already emailed." }, 400); up.status = "passed"; }
        else if (b.op === "restore") { if (m!.status !== "passed") return json({ error: "Not passed." }, 400); up.status = m!.subject ? "drafted" : "matched"; }
        else if (b.op === "edit") {
          if (!["drafted", "approved"].includes(m!.status)) return json({ error: "Only unsent drafts can be edited." }, 400);
          const subject = String(b.subject ?? "").trim().slice(0, 120), body = String(b.body ?? "").trim().slice(0, 4000);
          if (subject.length < 3 || body.length < 20) return json({ error: "Add a subject and a message." }, 400);
          up.subject = subject; up.body = body; up.status = "drafted";
        } else if (b.op === "meeting") {
          if (!["sent", "followed_up", "replied", "meeting"].includes(m!.status)) return json({ error: "Email them first." }, 400);
          up.status = "meeting"; up.meeting_note = String(b.note ?? "").trim().slice(0, 500) || null;
          const when = b.meeting_at ? new Date(String(b.meeting_at)) : null;
          up.meeting_at = when && !isNaN(+when) ? when.toISOString() : null;
        } else return json({ error: "Unknown action." }, 400);
        await db.from("irun_fund_matches").update(up).eq("id", id);
        if (b.op === "meeting") await log(c.id, "fundraise", "investor meeting booked");
        return json({ ok: true });
      }
      return json({ error: "Unknown action." }, 400);
    }

    return json({ error: "Unknown action." }, 400);
  } catch (e) {
    return json({ error: String(e instanceof Error ? e.message : e) }, 500);
  }
});
