// iRun Video: a member uploads a photo of themself + a song + a description of the video they want.
// iRun renders a music video or a short film starring them (engine/musicvideo.py, .github/workflows/video.yml).
// Membership comes from hsw_payments (same rules as hsw-join). Uploads go to the private irun-video bucket
// through signed upload URLs; finished videos land in the public irun-media bucket.
// Owner PIN session: a request with a verified owner token (header X-HSW-Owner or body owner_token) is the owner, with no
// video limit. Without a Supabase login it acts as the owner's own account (hsw365media@gmail.com) on this project.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type, authorization, apikey, x-client-info, x-hsw-owner", "Access-Control-Allow-Methods": "POST, OPTIONS" };
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

// Keep this list aligned with config/owners.json: every HSW365 owner login receives full access.
const OWNERS = [
  "hsw365media@gmail.com",
  "hoodstarent365@gmail.com",
  "book@hoodstar365.com",
  "elvintorressr@gmail.com",
  "emilymahan8792@gmail.com",
];
const DAY = 864e5;
// Videos per 30 days that come with each plan. Owners have no limit.
const LIMITS: Record<string, Record<string, number>> = { studio365: { starter: 1, plus: 3, pro: 5 } };
const PLAN_DAYS = 30;
const PHOTO = ["image/jpeg", "image/png", "image/webp"];
const SONG = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "audio/mp4", "audio/x-m4a", "audio/aac", "audio/ogg", "audio/flac"];
const EXT: Record<string, string> = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac", "audio/ogg": "ogg", "audio/flac": "flac" };
const STYLES = ["cinematic", "street", "neon", "luxury", "dark", "dreamy", "vintage", "anime", "performance"];

type Who = { id: string; email?: string; pin?: boolean };
const OWNER_EMAIL = OWNERS[0];
let ownerAccount: Who | null = null;
// The owner's own Supabase account, for a PIN session that has no Supabase login on this device.
async function ownerUser(): Promise<Who | null> {
  if (ownerAccount) return ownerAccount;
  for (let page = 1; page <= 50; page++) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 200 });
    if (error || !data) break;
    const u = data.users.find((x) => (x.email || "").toLowerCase() === OWNER_EMAIL);
    if (u) return (ownerAccount = { id: u.id, email: u.email, pin: true });
    if (data.users.length < 200) break;
  }
  return null;
}

async function who(req: Request, b: Record<string, unknown>): Promise<Who | null> {
  const pin = await ownerPin(req, b);
  const t = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (t) {
    const { data } = await admin.auth.getUser(t);
    if (data.user) return { id: data.user.id, email: data.user.email, pin };
  }
  return pin ? await ownerUser() : null;
}

async function membership(app: string, user: Who) {
  const email = (user.email || "").trim().toLowerCase();
  if (user.pin || OWNERS.includes(email)) return { email, active: true, owner: true, plan: "pro" };
  const { data: rows } = await admin.from("hsw_payments").select("plan,status,created_at,decided_at,grace_until")
    .eq("app", app).eq("account_ref", user.id).order("created_at", { ascending: true });
  let until = 0, plan: string | null = null;
  for (const r of rows || []) {
    if (r.status === "approved") {
      until = Math.max(until, new Date(r.decided_at || r.created_at).getTime()) + PLAN_DAYS * DAY; plan = r.plan;
    } else if (r.status === "pending" && r.grace_until && new Date(r.grace_until).getTime() > until) {
      until = new Date(r.grace_until).getTime(); plan = r.plan;
    }
  }
  return { email, active: until > Date.now(), owner: false, plan };
}

async function quota(app: string, user: Who) {
  const m = await membership(app, user);
  const { count } = await admin.from("irun_video_jobs").select("id", { count: "exact", head: true })
    .eq("user_id", user.id).neq("status", "failed").gte("created_at", new Date(Date.now() - PLAN_DAYS * DAY).toISOString());
  const limit = m.owner ? null : (m.active && m.plan ? LIMITS[app]?.[m.plan] ?? 0 : 0);
  const used = count || 0;
  return { ...m, used, limit, left: limit == null ? null : Math.max(0, limit - used), limits: LIMITS[app] };
}

async function dispatch(id: string) {
  const tok = Deno.env.get("GH_DISPATCH_TOKEN");
  if (!tok) return false; // the scheduled run in iRun picks the job up within a few minutes
  const r = await fetch("https://api.github.com/repos/HSW365/iRUN/dispatches", {
    method: "POST", headers: { authorization: `Bearer ${tok}`, accept: "application/vnd.github+json", "user-agent": "irun-video" },
    body: JSON.stringify({ event_type: "irun-video", client_payload: { id } }),
  }).catch(() => null);
  return !!r && r.ok;
}

const clean = (s: unknown, n: number) => String(s ?? "").replace(/[\u0000-\u001f]/g, " ").trim().slice(0, n);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const b = await req.json().catch(() => ({}));
  const app = String(b.app || "studio365");
  if (!LIMITS[app]) return json({ error: "Unknown app" }, 400);
  const user = await who(req, b);
  if (!user) return json({ error: (b.owner_token || req.headers.get("x-hsw-owner")) ? "Owner session not accepted, or the owner account hsw365media@gmail.com has no login on this project yet. Sign in with your PIN again." : "Log in first" }, 401);

  if (b.a === "quota") return json(await quota(app, user));

  if (b.a === "upload") {
    const kind = String(b.kind || ""), type = String(b.type || "").toLowerCase(), size = Number(b.size || 0);
    const ok = kind === "photo" ? PHOTO : kind === "song" ? SONG : null;
    if (!ok) return json({ error: "Unknown upload" }, 400);
    if (!ok.includes(type)) return json({ error: kind === "photo" ? "Use a JPG, PNG or WEBP photo." : "Use an MP3, WAV, M4A, AAC, OGG or FLAC song." }, 400);
    const max = kind === "photo" ? 15 : 50;
    if (!(size > 0) || size > max * 1048576) return json({ error: `That file is too big (${max} MB max).` }, 400);
    const path = `${user.id}/${kind}-${crypto.randomUUID()}.${EXT[type]}`;
    const { data, error } = await admin.storage.from("irun-video").createSignedUploadUrl(path);
    if (error || !data) return json({ error: error?.message || "Upload failed. Try again." }, 500);
    return json({ path, url: data.signedUrl });
  }

  if (b.a === "create") {
    const q = await quota(app, user);
    if (!q.active) return json({ error: "Join a plan to make videos.", need: "plan" }, 402);
    if (q.left !== null && q.left <= 0) return json({ error: `You've used all ${q.limit} videos on your plan this month.`, need: "upgrade" }, 402);
    const kind = ["short_film", "ugc"].includes(b.kind) ? b.kind : "music_video";
    const description = clean(b.description, 2000);
    if (description.length < 10) return json({ error: "Describe the video you want (a sentence or two)." }, 400);
    const photo = String(b.photo_path || ""), song = String(b.song_path || "");
    if (!photo.startsWith(user.id + "/photo-")) return json({ error: "Upload your photo first." }, 400);
    if (song ? !song.startsWith(user.id + "/song-") : kind !== "ugc") return json({ error: "Upload your song first." }, 400);
    const style = STYLES.includes(String(b.style)) ? String(b.style) : "cinematic";
    const length = [15, 30, 45, 60, 90, 120].includes(Number(b.length)) ? Number(b.length) : (kind === "ugc" ? 30 : 60);
    const { data: active } = await admin.from("irun_video_jobs").select("id").eq("user_id", user.id).in("status", ["queued", "rendering"]);
    if ((active || []).length >= 2 && !q.owner) return json({ error: "You have 2 videos rendering. Start the next one when one finishes." }, 409);
    const { data, error } = await admin.from("irun_video_jobs").insert({
      user_id: user.id, email: q.email, app, kind, description, style, length_s: length,
      title: clean(b.title, 80) || null, artist: clean(b.artist, 80) || null, photo_path: photo, song_path: song || null,
    }).select("id,kind,status,created_at").single();
    if (error) return json({ error: error.message }, 400);
    await dispatch(data.id);
    return json({ job: data, quota: await quota(app, user) });
  }

  if (b.a === "list") {
    const { data } = await admin.from("irun_video_jobs")
      .select("id,kind,title,artist,style,length_s,status,progress,stage,video_url,poster_url,error,created_at,finished_at")
      .eq("user_id", user.id).order("created_at", { ascending: false }).limit(24);
    return json({ jobs: data || [] });
  }

  return json({ error: "Unknown action" }, 400);
});
