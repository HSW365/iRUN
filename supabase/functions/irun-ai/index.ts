// Central iRun AI gateway. Browser clients send work to iRun; provider keys stay server-side.
import { createClient } from "jsr:@supabase/supabase-js@2";

const URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const API_KEY = Deno.env.get("ANTHROPIC_API_KEY") ?? "";
const MODEL = Deno.env.get("IRUN_MODEL") ?? "claude-sonnet-4-5";
const db = createClient(URL, SERVICE, { auth: { persistSession: false } });
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  if (req.method !== "POST") return json({ error: "Use POST." }, 405);
  try {
    const body = await req.json();
    const owner = String(body.owner ?? "");
    if (!owner) return json({ error: "Sign in to iRun before using its AI agents." }, 401);
    const { data: setting } = await db.from("irun_settings").select("value").eq("key", "owner_key").maybeSingle();
    if (!setting?.value || owner !== setting.value) return json({ error: "iRun owner session is not authorized. Sign in again." }, 401);
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
