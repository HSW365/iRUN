import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const GRAPH = "https://graph.instagram.com/v23.0";

let cache: Record<string, string> = {};
let cacheAt = 0;
async function cfg(): Promise<Record<string, string>> {
  if (Date.now() - cacheAt < 30_000) return cache;
  const { data } = await db.from("irun_ig_config").select("key,value");
  cache = Object.fromEntries((data ?? []).map((r: any) => [r.key, r.value]));
  cacheAt = Date.now();
  return cache;
}

async function validSig(body: string, header: string | null, secret?: string) {
  if (!secret) return true; // secret not loaded yet
  if (!header?.startsWith("sha256=")) return false;
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)));
  const hex = [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
  const want = header.slice(7);
  if (hex.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < hex.length; i++) d |= hex.charCodeAt(i) ^ want.charCodeAt(i);
  return d === 0;
}

const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/;
const PHONE = /(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/;

async function sendDM(token: string, igId: string, to: string, text: string) {
  const r = await fetch(`${GRAPH}/${igId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ recipient: { id: to }, message: { text } }),
  });
  return r.ok;
}

async function handleDM(c: Record<string, string>, igId: string, m: any) {
  const sender = m.sender?.id;
  const text: string | undefined = m.message?.text;
  if (!sender || sender === igId || m.message?.is_echo) return;
  await db.from("irun_ig_events").insert({ kind: "dm", ig_account_id: igId, sender_id: sender, text, raw: m });
  const email = text?.match(EMAIL)?.[0] ?? null;
  const phone = text?.match(PHONE)?.[0] ?? null;
  const { data: lead } = await db.from("irun_ig_leads").select("*").eq("sender_id", sender).maybeSingle();
  if (lead) {
    await db.from("irun_ig_leads").update({
      last_message: text, last_seen: new Date().toISOString(), message_count: lead.message_count + 1,
      email: lead.email ?? email, phone: lead.phone ?? phone,
    }).eq("sender_id", sender);
  } else {
    await db.from("irun_ig_leads").insert({ sender_id: sender, ig_account_id: igId, first_message: text, last_message: text, email, phone });
  }
  if (c.auto_reply_enabled === "true" && c.access_token && !lead?.replied) {
    if (await sendDM(c.access_token, igId, sender, c.auto_reply_text)) {
      await db.from("irun_ig_leads").update({ replied: true }).eq("sender_id", sender);
    }
  }
}

// --- Growth: reply publicly to every comment on our own posts (once per person per post per day).
// Answering comments fast tells Instagram to push the Reel to more people.
// Off switch: irun_ig_config key comment_replies = "false". Needs ANTHROPIC_API_KEY secret.
async function commentReply(text: string, username?: string): Promise<string | null> {
  const key = Deno.env.get("ANTHROPIC_API_KEY");
  if (!key || !text.trim()) return null;
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({
      model: "claude-haiku-4-5", max_tokens: 120,
      system: "You are Hoodstar365 (Elvin Torres Sr.), U.S. Army veteran, author and artist whose message is Turn Negative Into Positive. " +
        "Reply to an Instagram comment on your own post in 1 short sentence (max 20 words), real and warm, like a person, never salesy. " +
        "If they ask a question, answer briefly or invite them to DM. No emojis, no hashtags, no links, no promises. " +
        "If the comment is spam, hateful or from a bot, reply with exactly SKIP.",
      messages: [{ role: "user", content: `@${username ?? "someone"} commented: ${text.slice(0, 500)}` }],
    }),
  });
  if (!r.ok) return null;
  const j = await r.json();
  const out = (j.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("").trim();
  return !out || out === "SKIP" ? null : out.slice(0, 300);
}

// iRun's engine keeps the live, auto-refreshed Instagram token in irun_tokens.
async function igToken(c: Record<string, string>): Promise<string | null> {
  if (c.access_token) return c.access_token;
  const { data } = await db.from("irun_tokens").select("value").eq("name", "instagram:hoodstar365").maybeSingle();
  return data?.value ?? null;
}

async function handleComment(c: Record<string, string>, igId: string, v: any) {
  const uid = String(v.from?.id ?? "");
  const mediaId = String(v.media?.id ?? "");
  if (c.comment_replies === "false" || !uid || uid === igId || v.parent_id || !mediaId) return;
  const token = await igToken(c);
  if (!token) return;
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const { data: done } = await db.from("irun_ig_events").select("id").eq("kind", `comment_reply:${mediaId}`)
    .eq("sender_id", uid).gte("received_at", since).limit(1);
  if ((done ?? []).length) return;
  const reply = await commentReply(v.text ?? "", v.from?.username).catch(() => null);
  if (!reply) return;
  const r = await fetch(`${GRAPH}/${v.id}/replies`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message: reply }),
  });
  await db.from("irun_ig_events").insert({
    kind: `comment_reply:${mediaId}`, ig_account_id: igId, sender_id: uid, text: reply,
    raw: { ok: r.ok, status: r.status, comment_id: v.id },
  });
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const c = await cfg();

  if (req.method === "GET") {
    const mode = url.searchParams.get("hub.mode");
    const token = url.searchParams.get("hub.verify_token");
    const challenge = url.searchParams.get("hub.challenge");
    if (mode === "subscribe" && token && token === c.verify_token && challenge) {
      return new Response(challenge, { status: 200, headers: { "Content-Type": "text/plain" } });
    }
    return new Response("forbidden", { status: 403 });
  }

  if (req.method !== "POST") return new Response("method not allowed", { status: 405 });

  const body = await req.text();
  if (!(await validSig(body, req.headers.get("x-hub-signature-256"), c.app_secret))) {
    return new Response("bad signature", { status: 401 });
  }

  let payload: any;
  try { payload = JSON.parse(body); } catch { return new Response("ok"); }

  const work = (async () => {
    for (const entry of payload.entry ?? []) {
      const igId = String(entry.id ?? "");
      for (const m of entry.messaging ?? []) await handleDM(c, igId, m);
      for (const ch of entry.changes ?? []) {
        const v = ch.value ?? {};
        await db.from("irun_ig_events").insert({
          kind: ch.field ?? "change", ig_account_id: igId, sender_id: v.from?.id ?? null, text: v.text ?? null, raw: ch,
        });
        if (ch.field === "comments") await handleComment(c, igId, v).catch((e) => console.error("comment reply", e));
      }
    }
  })().catch((e) => console.error("irun-ig-webhook", e));

  // @ts-ignore EdgeRuntime is provided by Supabase
  if (typeof EdgeRuntime !== "undefined") EdgeRuntime.waitUntil(work); else await work;
  return new Response("EVENT_RECEIVED", { status: 200 });
});
