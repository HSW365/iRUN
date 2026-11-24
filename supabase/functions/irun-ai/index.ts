// Central iRun AI gateway. Browser clients send work to iRun; provider keys stay server-side.
import { createClient } from "jsr:@supabase/supabase-js@2";

const URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const API_KEY = Deno.env.get("ANTHROPIC_API_KEY") ?? "";
const MODEL = Deno.env.get("IRUN_MODEL") ?? "claude-sonnet-4-5";
const db = createClient(URL, SERVICE, { auth: { persistSession: false } });
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-hsw-owner",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

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

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  if (req.method !== "POST") return json({ error: "Use POST." }, 405);
  try {
    const body = await req.json();
    // The owner signs in with the owner PIN (owner_token) or the older owner key; either one is checked here.
    const owner = String(body.owner ?? "");
    const pin = await ownerPin(req, body);
    if (!owner && !pin) return json({ error: "Sign in to iRun before using its AI agents. Tap Owner login and enter your PIN." }, 401);
    if (!pin) {
      const { data: setting } = await db.from("irun_settings").select("value").eq("key", "owner_key").maybeSingle();
      if (!setting?.value || owner !== setting.value) return json({ error: "iRun owner session is not authorized. Tap Owner login and enter your PIN." }, 401);
    }
    if (!API_KEY) return json({ error: "iRun AI is not configured yet. Add ANTHROPIC_API_KEY to the Supabase Edge Function secrets, then redeploy irun-ai." }, 503);

    const system = String(body.system ?? "").slice(0, 16000);
    const messages = Array.isArray(body.messages) ? body.messages.slice(-12).map((m: any) => ({
      role: m?.role === "assistant" ? "assistant" : "user",
      content: String(m?.content ?? "").slice(0, 12000),
    })).filter((m: any) => m.content.trim()) : [];
    if (!system || !messages.length) return json({ error: "Add an instruction and a message for the iRun agent." }, 400);
    const max = Math.max(128, Math.min(8000, Math.floor(Number(body.max_tokens) || 3500)));
    const model = String(body.model || MODEL).slice(0, 100);
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model, max_tokens: max, system, messages }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = result?.error?.message || `AI provider returned HTTP ${response.status}`;
      const status = response.status === 429 ? 429 : response.status === 401 ? 503 : 502;
      return json({ error: message, provider_status: response.status, retryable: response.status === 429 || response.status >= 500 }, status);
    }
    const text = (result.content ?? []).filter((part: any) => part.type === "text").map((part: any) => part.text).join("");
    if (!text.trim()) return json({ error: "The iRun AI provider returned an empty response. Try again." }, 502);
    return json({ text, model: result.model ?? model, usage: result.usage ?? null });
  } catch (error) {
    console.error("iRun AI gateway error", error);
    return json({ error: error instanceof Error ? error.message : "iRun AI request failed." }, 500);
  }
});
