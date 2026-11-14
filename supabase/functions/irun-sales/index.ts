// iRun Sales Agent: "get me customers" -> a real lead list with emails -> a personal draft for every lead -> approve -> sent.
// Follow-ups (4 days later) and reply answering run on the hourly Sales Autopilot (engine/sales.py).
//   POST {a:"apps", owner}                                            -> apps the agent can sell
//   POST {a:"find", owner, app, ask?, where, limit?}                  -> finds leads, saves them as drafts, returns them
//   POST {a:"add", owner, app, campaign?, rows:[{email,business,contact?,city?,note?}]}  -> your own list, drafted
//   POST {a:"scrape", owner, sites:[url...]}                          -> {url: email|null} from each site
//   POST {a:"site", owner, url}                                       -> reads a pasted website, returns {profile, buyers:[{label, filters}]} (who would buy from it)
//   POST {a:"enrich", owner, seller?, leads:[{email,business,website,trade,city}]} -> {why:{email: "why now" line}} from each prospect's own site
//   (add/find also accept app:"custom" + seller:{name,pitch,offer,link,cta} for a pasted site, and rows with why/lat/lon/distance_mi)
//   POST {a:"list", owner, status?, campaign?}                        -> pipeline rows + counts
//   POST {a:"edit", owner, email, subject?, body?, followup_body?}
//   POST {a:"approve", owner, emails:[...]}                           -> sends now (daily cap), rest go out on the next hourly run
//   POST {a:"reject", owner, emails:[...]}
// Every action needs the iRun owner key (irun_settings.owner_key). Leads come from OpenStreetMap (free) plus the email
// published on each business's own website. Mail goes through the CallTwin relay, same as the Sales Autopilot.
import { createClient } from "jsr:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const GROQ = Deno.env.get("GROQ_API_KEY") ?? "";
const UA = "HSW365-iRun-SalesAgent/1.0 (hsw365media@gmail.com)";
const ADDRESS = "HSW365 Media LLC, Hammonton, NJ 08037";
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
const esc = (s: string) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
const EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const JUNK = /(example\.|domain\.com|sentry|wixpress|godaddy|\.png|\.jpg|\.gif|\.webp|\.svg|@2x|noreply|no-reply|donotreply|privacy|abuse|postmaster|webmaster|legal@|yourname|email@|user@|name@|test@)/i;

// ---------------------------------------------------------------- apps
type App = { id: string; name: string; link: string; signup?: string; who: string; hook: string; pitch: string; offer: string; cta: string; targets: string[] };
const APPS: App[] = [
  { id: "calltwin", name: "CallTwin", link: "https://hsw365.github.io/calltwin/", signup: "https://hsw365.github.io/calltwin/signup.html",
    who: "service businesses", hook: "never miss another job call",
    pitch: "CallTwin is an AI receptionist that answers every call, text and website chat 24/7, takes the customer's name, number, address and the job, and sends it straight to your phone. Jobs go to whoever answers first, and CallTwin always answers.",
    offer: "$500 setup, 14 days free, then plans from $49/mo.", cta: "set {biz} up with a free 14-day trial", targets: ["trades"] },
  { id: "queenee", name: "QUEENEE", link: "https://hsw365.github.io/queenee/",
    who: "local businesses", hook: "a website that brings you customers",
    pitch: "QUEENEE builds you a mobile-first website made to get calls and bookings, on your own domain, with hosting and updates included. No templates, built from your business.",
    offer: "Website builds from $1,500, hosting and updates included.", cta: "send a free mockup of the new {biz} site", targets: ["shops", "food"] },
  { id: "ultimate", name: "HSW365 AI Front Office", link: "https://hsw365.net/pages/ai-front-office",
    who: "business owners", hook: "your whole front office on AI",
    pitch: "One package runs your front office: a QUEENEE website, CallTwin answering every call and text 24/7, and iRun posting your business on Instagram every day.",
    offer: "Website + CallTwin from $2,500.", cta: "send {biz} a free estimate", targets: ["trades", "shops", "food", "health"] },
  { id: "operator", name: "iRun Operator", link: "https://hsw365.github.io/iRUN/start.html",
    who: "small business owners", hook: "your marketing on autopilot",
    pitch: "Give iRun Operator your website and it runs your marketing: posts videos every day, emails your prospects and sends you a report every night. No agency, no cut of your sales.",
    offer: "Plans from $15/mo.", cta: "show you what iRun would post for {biz} this week", targets: ["food", "shops", "fitness"] },
  { id: "irun", name: "iRun", link: "https://hsw365.github.io/iRUN/",
    who: "brands and creators", hook: "daily content without the work",
    pitch: "iRun writes, voices, edits and posts short videos for your brand every day, and turns comments and DMs into leads automatically.",
    offer: "Plans from $15/mo.", cta: "make {biz} a free sample video", targets: ["shops", "fitness", "beauty"] },
  { id: "dispute365", name: "DISPUTE365", link: "https://hsw365.github.io/DISPUTE365/",
    who: "businesses whose customers need better credit", hook: "help your customers get approved",
    pitch: "DISPUTE365 is a self-help credit dispute app: your customers upload their reports, it finds the errors and writes the dispute letters for them. Refer the customers you can't get approved today.",
    offer: "Affordable monthly plan, no advance fees.", cta: "set {biz} up with a referral link", targets: ["auto", "realestate"] },
  { id: "flipit", name: "FLIPIT", link: "https://flipit-m5ig.onrender.com",
    who: "real estate pros", hook: "every deal number in one place",
    pitch: "FLIPIT is a deal workspace for flippers, wholesalers and agents: max offer, risk check, cash-buyer matching and paperwork in one place, plus a property preservation module for bank-owned homes.",
    offer: "Free to start.", cta: "give {biz} early access", targets: ["realestate"] },
  { id: "klipit", name: "Klipit", link: "https://klipit.onrender.com",
    who: "gaming spots and streamers", hook: "stream highlights clipped automatically",
    pitch: "Klipit takes a stream or VOD link and cuts the best moments into ready-to-post vertical clips automatically. Perfect for gaming lounges, esports teams and streamers.",
    offer: "Free tier, paid plans for more clips.", cta: "clip your next stream free", targets: ["gaming"] },
  { id: "studio", name: "HSW365studio", link: "https://hsw365.github.io/STUDIO365/",
    who: "music businesses", hook: "a recording studio in the browser",
    pitch: "HSW365studio is a browser-based recording studio: record, mix and master from any laptop, no gear. A great tool for your students and artists between sessions.",
    offer: "Subscription plans, free to try.", cta: "set {biz} up with free artist accounts", targets: ["music"] },
  { id: "stream", name: "HSW365 Stream", link: "https://hsw365stream.com",
    who: "churches and venues", hook: "go live with your own channel",
    pitch: "HSW365 Stream gives you your own live streaming and video channel: stream services and events, sell tickets or take donations, keep 100% of your audience.",
    offer: "Plans for every size.", cta: "set up a free test stream for {biz}", targets: ["worship", "venues"] },
  { id: "nil", name: "NIL365", link: "https://nil365.onrender.com",
    who: "schools and athletic programs", hook: "NIL deals for your athletes",
    pitch: "NIL365 is a sign-up platform that connects student athletes with local businesses for name, image and likeness deals, with profiles, deal tracking and payouts.",
    offer: "Free for athletes.", cta: "set up a free page for {biz} athletes", targets: ["schools", "sports"] },
  { id: "captureitlive", name: "CaptureItLive", link: "https://hsw365.github.io/captureitlive/",
    who: "yoga and fitness studios", hook: "your studio community online",
    pitch: "CaptureItLive gives your studio its own community app: class schedule, live and recorded classes, member posts and memberships in one place.",
    offer: "Free to start.", cta: "build {biz} a free community page", targets: ["fitness"] },
  { id: "speekzone", name: "SpeekZone", link: "https://hsw365.github.io/SPEEKZONE/",
    who: "community organizations", hook: "a voice for your community",
    pitch: "SpeekZone is a short-video community app where your members share stories and updates, a safe space built for your people.",
    offer: "Free, verified accounts $9.99.", cta: "set {biz} up with a verified page", targets: ["community"] },
  { id: "friendy", name: "Friendy", link: "https://hsw365.github.io/FRIENDY/",
    who: "community and senior centers", hook: "a friend that's always there",
    pitch: "Friendy is an AI companion app that keeps people company, checks in daily and helps with reminders. A gentle tool for members who live alone.",
    offer: "Free to try.", cta: "give {biz} members free access", targets: ["community"] },
  { id: "affiliate", name: "HSW365 Affiliates", link: "https://hsw365.net/pages/affiliates",
    who: "creators and business owners", hook: "20% recurring on every referral",
    pitch: "The HSW365 Affiliate Partner Program is free to join: earn 20% recurring commission on every subscriber you send to HSW365 apps like iRun, CallTwin and QUEENEE, paid monthly.",
    offer: "Free to join.", cta: "send your {biz} affiliate link", targets: ["shops", "fitness", "beauty"] },
  { id: "investor", name: "HSW365 Investor Partners", link: "https://hsw365.net",
    who: "investors", hook: "4 partner spots, $25K each",
    pitch: "I've built 15 live AI apps under HSW365, including iRun, CallTwin and QUEENEE, with CallTwin already sold to a paying customer. I'm bringing on 4 partners at $25,000 each for equity in the HSW365 app portfolio.",
    offer: "4 spots at $25,000 each.", cta: "walk you through the deck in 15 minutes", targets: [] },
];

// OpenStreetMap filters. Each value is a list of [key, regex].
const GROUPS: Record<string, [string, string][]> = {
  trades: [["craft", "plumber|hvac|roofer|electrician|carpenter|painter|builder|tiler|floorer|glaziery|locksmith|cleaning|insulation|handyman|landscaper|gardener"], ["office", "construction_company|contractor"]],
  shops: [["shop", "hairdresser|beauty|clothes|boutique|florist|bakery|jewelry|shoes|cosmetics|tattoo|gift"]],
  food: [["amenity", "restaurant|cafe|fast_food|bar|ice_cream"]],
  health: [["amenity", "dentist|clinic|doctors|veterinary"], ["healthcare", "chiropractor|physiotherapist|dentist"]],
  fitness: [["leisure", "fitness_centre|sports_centre"], ["sport", "yoga|pilates|fitness|martial_arts|boxing"]],
  beauty: [["shop", "hairdresser|beauty|massage|cosmetics|tattoo"], ["leisure", "spa"]],
  auto: [["shop", "car|car_repair|tyres|motorcycle"]],
  realestate: [["office", "estate_agent|property_management|mortgage"]],
  gaming: [["shop", "games|video_games|computer"], ["amenity", "internet_cafe"], ["leisure", "amusement_arcade"]],
  music: [["amenity", "studio|music_school"], ["shop", "music|musical_instrument"], ["craft", "musical_instrument"]],
  worship: [["amenity", "place_of_worship"]],
  venues: [["amenity", "events_venue|theatre|nightclub|conference_centre"]],
  schools: [["amenity", "school|college|university"]],
  sports: [["leisure", "sports_centre|stadium"], ["club", "sport"]],
  community: [["amenity", "community_centre|social_centre|social_facility"], ["office", "ngo|association|charity"]],
};
const WORDS: [RegExp, [string, string][]][] = [
  [/barber|hair/i, [["shop", "hairdresser"]]], [/nail|salon|beauty|lash|brow/i, [["shop", "beauty|hairdresser"]]],
  [/spa|massage/i, [["leisure", "spa"], ["shop", "massage"]]], [/tattoo/i, [["shop", "tattoo"]]],
  [/restaurant|food|diner|pizza|grill/i, [["amenity", "restaurant|fast_food"]]], [/cafe|coffee/i, [["amenity", "cafe"]]],
  [/bar\b|bars\b|lounge|pub/i, [["amenity", "bar|pub"]]], [/bakery|bakeries/i, [["shop", "bakery|pastry"]]],
  [/gym|fitness|crossfit/i, [["leisure", "fitness_centre"], ["sport", "fitness"]]], [/yoga|pilates/i, [["sport", "yoga|pilates"]]],
  [/boxing|martial|karate|jiu/i, [["sport", "boxing|martial_arts|karate"]]],
  [/plumb/i, [["craft", "plumber"]]], [/hvac|heating|air cond/i, [["craft", "hvac"]]], [/roof/i, [["craft", "roofer"]]],
  [/electric/i, [["craft", "electrician"]]], [/contractor|construction|builder|remodel/i, [["office", "construction_company|contractor"], ["craft", "builder|carpenter"]]],
  [/landscap|lawn|garden/i, [["craft", "landscaper|gardener"]]], [/clean/i, [["craft", "cleaning"]]], [/paint/i, [["craft", "painter"]]],
  [/locksmith/i, [["craft", "locksmith"]]], [/auto|mechanic|car repair|body shop/i, [["shop", "car_repair|tyres"]]],
  [/dealer/i, [["shop", "car|motorcycle"]]], [/dentist|dental/i, [["amenity", "dentist"]]], [/chiro/i, [["healthcare", "chiropractor"]]],
  [/doctor|clinic|medical/i, [["amenity", "clinic|doctors"]]], [/vet\b|veterinar|pet/i, [["amenity", "veterinary"], ["shop", "pet|pet_grooming"]]],
  [/lawyer|attorney|law firm/i, [["office", "lawyer"]]], [/account|tax|cpa/i, [["office", "accountant|tax_advisor"]]],
  [/insurance/i, [["office", "insurance"]]], [/real estate|realtor|realty|broker/i, [["office", "estate_agent"]]],
  [/mortgage|lender/i, [["office", "mortgage|financial"]]], [/church|ministr|worship|mosque|temple/i, [["amenity", "place_of_worship"]]],
  [/school|academy/i, [["amenity", "school"]]], [/college|universit/i, [["amenity", "college|university"]]],
  [/studio|music|record/i, [["amenity", "studio|music_school"], ["shop", "music|musical_instrument"]]],
  [/boutique|clothing|apparel|streetwear|fashion/i, [["shop", "clothes|boutique|shoes"]]], [/florist|flower/i, [["shop", "florist"]]],
  [/photograph/i, [["craft", "photographer"], ["shop", "photo"]]], [/daycare|child ?care|preschool/i, [["amenity", "childcare|kindergarten"]]],
  [/hotel|motel|inn\b/i, [["tourism", "hotel|motel|guest_house"]]], [/venue|event|banquet/i, [["amenity", "events_venue|conference_centre"]]],
  [/gaming|esport|arcade|video game/i, GROUPS.gaming], [/nonprofit|non-profit|charity|community/i, GROUPS.community],
  [/jewel/i, [["shop", "jewelry"]]], [/funeral/i, [["shop", "funeral_directors"]]], [/storage/i, [["shop", "storage_rental"]]],
];

function filtersFor(app: App, ask: string): [string, string][] {
  const hits = WORDS.filter(([re]) => re.test(ask)).flatMap(([, f]) => f);
  if (hits.length) return hits;
  return app.targets.flatMap((t) => GROUPS[t] ?? []);
}

// ---------------------------------------------------------------- finding
async function geocode(where: string) {
  // Photon (komoot, free, OpenStreetMap data). extent = [west, north, east, south].
  const j = await fetch(`https://photon.komoot.io/api/?limit=5&q=${encodeURIComponent(where)}`, { headers: { "User-Agent": UA } }).then((r) => r.json()).catch(() => null);
  const f = (j?.features ?? []).find((x: any) => x.properties?.countrycode === "US") ?? j?.features?.[0];
  if (!f) {
    // Fallback: Open-Meteo geocoding (free, no key). City name only, so drop the ", ST" part.
    const city = where.split(",")[0].trim();
    const st = (where.split(",")[1] ?? "").trim().toUpperCase();
    const g = await fetch(`https://geocoding-api.open-meteo.com/v1/search?count=10&countryCode=US&name=${encodeURIComponent(city)}`).then((r) => r.json()).catch(() => null);
    const hit = (g?.results ?? []).find((x: any) => !st || x.admin1_code === st || (x.admin1 ?? "").toUpperCase().startsWith(st)) ?? g?.results?.[0];
    if (!hit) throw new Error(`Couldn't find "${where}" on the map. Try "City, ST".`);
    return box(hit.latitude - 0.05, hit.latitude + 0.05, hit.longitude - 0.05, hit.longitude + 0.05, `${hit.name}, ${hit.admin1 ?? ""}`);
  }
  const [lon, lat] = f.geometry.coordinates;
  const ext = f.properties.extent ?? [lon - 0.05, lat + 0.05, lon + 0.05, lat - 0.05];
  const [w, n, e, s] = ext.map(Number);
  const p = f.properties;
  const name = [p.name, p.state].filter(Boolean).join(", ");
  return box(s, n, w, e, name);
}
function box(s: number, n: number, w: number, e: number, name: string) {
  const small = (n - s) < 0.3; // a town: widen to roughly 25 miles around it
  const pad = small ? 0.3 : 0;
  return { bbox: `${(s - pad).toFixed(4)},${(w - pad).toFixed(4)},${(n + pad).toFixed(4)},${(e + pad).toFixed(4)}`, label: name };
}

async function overpass(q: string) {
  for (const url of ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]) {
    try {
      const r = await fetch(url, { method: "POST", headers: { "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded" }, body: "data=" + encodeURIComponent(q), signal: AbortSignal.timeout(45_000) });
      if (r.ok) return (await r.json()).elements ?? [];
    } catch (_) { /* next mirror */ }
  }
  throw new Error("The map service is busy right now. Try again in a minute.");
}

async function siteEmail(site: string): Promise<string | null> {
  let base: URL;
  try { base = new URL(site.startsWith("http") ? site : "https://" + site); } catch { return null; }
  const host = base.hostname.replace(/^www\./, "");
  for (const path of ["", "/contact", "/contact-us"]) {
    try {
      const r = await fetch(new URL(path || "/", base).toString(), { headers: { "User-Agent": "Mozilla/5.0 (compatible; HSW365-iRun)" }, redirect: "follow", signal: AbortSignal.timeout(6000) });
      if (!r.ok) continue;
      const html = (await r.text()).slice(0, 400_000);
      const found = [...html.matchAll(/(?:mailto:)?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})/g)].map((m) => m[1].toLowerCase())
        .filter((e) => EMAIL.test(e) && !JUNK.test(e));
      if (found.length) return found.find((e) => e.endsWith("@" + host)) ?? found[0];
    } catch (_) { /* next page */ }
  }
  return null;
}

type Lead = { email: string; business: string; trade: string; city: string | null; state: string | null; website: string | null };

async function findLeads(app: App, ask: string, where: string, limit: number) {
  const filters = filtersFor(app, ask);
  if (!filters.length) throw new Error(`Tell me who to target for ${app.name}, e.g. "barbershops" or "churches".`);
  const { bbox, label } = await geocode(where);
  const parts = filters.map(([k, re]) => `nwr["${k}"~"^(${re})$"]["name"](${bbox});`);
  const els = await overpass(`[out:json][timeout:50];(${parts.join("")});out tags 1500;`);
  const have = new Set((await db.from("irun_suppress").select("email")).data?.map((r) => r.email) ?? []);
  const seen = new Set<string>();
  const out: Lead[] = [];
  const needSite: { t: Record<string, string>; site: string }[] = [];
  const mk = (t: Record<string, string>, email: string): Lead => ({
    email, business: t.name.slice(0, 120),
    trade: (Object.entries(t).find(([k]) => ["craft", "shop", "amenity", "office", "leisure", "sport", "healthcare", "tourism"].includes(k))?.[1] ?? "local business").replace(/_/g, " ").slice(0, 60),
    city: (t["addr:city"] ?? "").slice(0, 80) || null, state: (t["addr:state"] ?? "").slice(0, 20) || null,
    website: (t.website ?? t["contact:website"] ?? null),
  });
  for (const el of els) {
    const t = el.tags ?? {};
    const raw = (t.email ?? t["contact:email"] ?? "").split(";")[0].trim().toLowerCase();
    if (raw && EMAIL.test(raw) && !JUNK.test(raw)) {
      if (!seen.has(raw) && !have.has(raw)) { seen.add(raw); out.push(mk(t, raw)); }
    } else if (t.website || t["contact:website"]) needSite.push({ t, site: t.website ?? t["contact:website"] });
  }
  // Pull the email off each business's own website until we have enough.
  for (let i = 0; i < needSite.length && out.length < limit; i += 10) {
    const got = await Promise.all(needSite.slice(i, i + 10).map(async (x) => ({ x, e: await siteEmail(x.site) })));
    for (const { x, e } of got) if (e && !seen.has(e) && !have.has(e)) { seen.add(e); out.push(mk(x.t, e)); }
  }
  // Skip anyone already in the pipeline.
  const emails = out.map((l) => l.email);
  const known = new Set(emails.length ? ((await db.from("irun_sales_leads").select("email").in("email", emails)).data ?? []).map((r) => r.email) : []);
  return { leads: out.filter((l) => !known.has(l.email)).slice(0, limit), label, scanned: els.length };
}

// ---------------------------------------------------------------- pasted site + "why now"
const SAFE_KEYS = new Set(["craft", "shop", "amenity", "office", "leisure", "sport", "healthcare", "tourism", "club"]);
const SAFE_RE = /^[a-z_|]{2,120}$/;
function customApp(s: Record<string, string>): App {
  const name = String(s.name || "this business").slice(0, 80), link = /^https?:\/\//.test(s.link ?? "") ? s.link : "https://hsw365.net";
  return { id: "custom", name, link, who: "local businesses", hook: String(s.hook || `how ${name} can help`).slice(0, 100),
    pitch: String(s.pitch || `${name} helps local businesses.`).slice(0, 500), offer: String(s.offer || "").slice(0, 200),
    cta: String(s.cta || "send you the details for {biz}").slice(0, 160), targets: [] };
}
async function pageText(site: string, max = 3500): Promise<{ text: string; title: string; desc: string } | null> {
  let u: URL;
  try { u = new URL(site.startsWith("http") ? site : "https://" + site); } catch { return null; }
  if (!/^https?:$/.test(u.protocol) || /^(localhost|127\.|10\.|192\.168\.|169\.254\.)/.test(u.hostname)) return null; // no internal hosts
  try {
    const r = await fetch(u.toString(), { headers: { "User-Agent": "Mozilla/5.0 (compatible; HSW365-iRun)" }, redirect: "follow", signal: AbortSignal.timeout(7000) });
    if (!r.ok) return null;
    const html = (await r.text()).slice(0, 500_000);
    const title = html.match(/<title[^>]*>([^<]*)/i)?.[1]?.trim() ?? "";
    const desc = html.match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)/i)?.[1]?.trim() ?? "";
    const text = html.replace(/<(script|style|noscript|svg)[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")
      .replace(/\s+/g, " ").trim().slice(0, max);
    return { text, title, desc };
  } catch { return null; }
}
async function llmJson(system: string, user: string): Promise<any | null> {
  if (!GROQ) return null;
  try {
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST", headers: { Authorization: "Bearer " + GROQ, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "llama-3.3-70b-versatile", temperature: 0.3, response_format: { type: "json_object" },
        messages: [{ role: "system", content: system }, { role: "user", content: user }] }),
      signal: AbortSignal.timeout(25000),
    });
    return JSON.parse((await r.json()).choices[0].message.content);
  } catch { return null; }
}
async function readSite(url: string) {
  const pg = await pageText(url, 4000);
  if (!pg) throw new Error("Couldn't open that site. Check the address.");
  const o = await llmJson(
    `You read a business website and work out who would buy from it. Return JSON: {"name": business name, "summary": one plain sentence on what they sell, "pitch": 2 sentences for a cold email, only facts on the page, "offer": price or offer only if the page states one else "", "hook": 6-10 word benefit, "buyers": up to 4 objects {"label": short plural name of a type of local business that would buy this e.g. "hospice care providers", "osm": array of [key,regex] pairs for OpenStreetMap tags that find them, key one of craft|shop|amenity|office|leisure|sport|healthcare|tourism, regex like "hospice|nursing_home"}}. Never invent facts.`,
    `Title: ${pg.title}\nDescription: ${pg.desc}\nPage text: ${pg.text}`);
  const buyers = (o?.buyers ?? []).slice(0, 4).map((x: any) => ({
    label: String(x.label ?? "").slice(0, 60),
    filters: (x.osm ?? []).filter((f: any) => Array.isArray(f) && SAFE_KEYS.has(f[0]) && SAFE_RE.test(String(f[1]))).slice(0, 6),
  })).filter((x: any) => x.label);
  return {
    profile: { name: String(o?.name || pg.title.split(/[|\-–·]/)[0].trim() || new URL(url.startsWith("http") ? url : "https://" + url).hostname).slice(0, 80),
      summary: String(o?.summary || pg.desc).slice(0, 240), pitch: String(o?.pitch || pg.desc).slice(0, 500), offer: String(o?.offer ?? "").slice(0, 200),
      hook: String(o?.hook || "").slice(0, 100), link: url.startsWith("http") ? url : "https://" + url },
    buyers, ai: !!o,
  };
}
// A real "why now" for one prospect, taken only from the text of their own site. No signal on the page -> empty string (never made up).
async function whyNow(seller: Record<string, string> | null, leads: Record<string, string>[]) {
  const pages = await Promise.all(leads.map(async (l) => ({ l, pg: l.website ? await pageText(l.website, 2500) : null })));
  const out: Record<string, string> = {};
  const usable = pages.filter((x) => x.pg?.text);
  const o = usable.length ? await llmJson(
    `For each prospect, find ONE specific, recent-looking reason to reach out now, using ONLY the text of that prospect's own website (new location, expansion, hiring, new service, event, season, growth, a stated need). Write it as a short factual phrase under 22 words, no flattery. If the text has no real signal, return an empty string for that email. Never invent anything. Seller: ${seller?.name ?? "HSW365"} - ${seller?.pitch ?? ""}. Return JSON {"why": {"<email>": "<phrase>"}}.`,
    usable.map((x) => `EMAIL ${x.l.email}\nBUSINESS ${x.l.business}\nSITE TEXT ${x.pg!.text}`).join("\n\n---\n\n")) : null;
  for (const l of leads) {
    const w = String(o?.why?.[l.email] ?? "").trim().replace(/\s+/g, " ");
    out[l.email] = w.length >= 12 ? w.slice(0, 200) : "";
  }
  return out;
}

// ---------------------------------------------------------------- drafts
const domain = (w: string | null) => { try { return w ? new URL(w.startsWith("http") ? w : "https://" + w).hostname.replace(/^www\./, "") : ""; } catch { return ""; } };
function draft(app: App, l: { business: string; trade?: string | null; city?: string | null; website?: string | null; contact?: string | null; note?: string | null; why?: string | null }) {
  const biz = l.business, who = (l.contact ?? "").trim() || `${biz} team`;
  const seen = l.website ? `I came across ${esc(biz)}${l.city ? " in " + esc(l.city) : ""} and checked out ${esc(domain(l.website))}.`
    : `I came across ${esc(biz)}${l.city ? " in " + esc(l.city) : ""}.`;
  const intro = app.id === "investor"
    ? `<p>I'm Elvin Torres Sr., U.S. Army veteran and solo founder of HSW365 Media LLC in South Jersey.${l.note ? " " + esc(l.note) : ""}</p>`
    : `<p>I'm Elvin Torres Sr., Army veteran and founder of HSW365 Media${app.id === "custom" ? `, and I'm reaching out on behalf of ${esc(app.name)}` : ""}. ${seen}</p>` +
      (l.why ? `<p>${esc(l.why.replace(/[.\s]+$/, ""))}, so I thought this was worth a note.</p>` : "");
  const cta = app.cta.replace("{biz}", biz);
  const body = `<p>Hi ${esc(who)},</p>${intro}<p>${esc(app.pitch)}</p><p>${app.offer ? `<b>${esc(app.offer)}</b> ` : ""}Details: <a href="${app.signup ?? app.link}">${esc(app.name)}</a></p>` +
    (app.id === "investor" ? `<p>Are you open to a 15-minute call this week? I'll send the deck ahead of time.</p>` : `<p>Reply <b>"YES"</b> and I'll ${esc(cta)}.</p>`);
  const subject = app.id === "investor" ? "Army veteran founder, 15 live AI apps, 4 partner spots" : `${biz}: ${app.hook}`;
  const followup = `<p>Hi ${esc(who)},</p><p>Bumping my note about ${esc(app.name)} for ${esc(biz)}: ${esc(app.hook)}. ${esc(app.offer)}</p>` +
    `<p><a href="${app.signup ?? app.link}">${esc(app.name)}</a></p><p>If it's a fit, reply "YES" and I'll ${esc(cta)}. If not, no problem.</p>`;
  return { subject, body, followup_body: followup };
}
async function polish(app: App, l: { business: string; trade?: string | null; city?: string | null; website?: string | null }, d: { subject: string; body: string }) {
  if (!GROQ) return d;
  try {
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST", headers: { Authorization: "Bearer " + GROQ, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "llama-3.3-70b-versatile", temperature: 0.5, response_format: { type: "json_object" }, messages: [
        { role: "system", content: "Rewrite this cold email so it reads like Elvin wrote it personally to this one business. Keep every fact, price, link and the YES call to action exactly. Max 110 words, no emojis, no exclamation marks, no new claims. Keep the sentence that explains why I'm writing now, if there is one. Return JSON {subject, body_html} with simple <p> paragraphs." },
        { role: "user", content: `Business: ${l.business} (${l.trade}, ${l.city ?? ""}). Website: ${l.website ?? "none"}\nSubject: ${d.subject}\n${d.body}` }] }),
      signal: AbortSignal.timeout(15000),
    });
    const o = JSON.parse((await r.json()).choices[0].message.content);
    return o.subject && o.body_html?.includes("YES") ? { subject: String(o.subject).slice(0, 140), body: o.body_html } : d;
  } catch { return d; }
}

// ---------------------------------------------------------------- sending
const wrap = (inner: string) => `<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;color:#111;font-size:15px;line-height:1.55">${inner}` +
  `<p>Elvin Torres Sr.<br>Founder, HSW365 Media LLC &middot; Veteran-owned<br><a href="https://hsw365.net">hsw365.net</a></p>` +
  `<p style="font-size:12px;color:#888;border-top:1px solid #eee;padding-top:10px">${ADDRESS}. Not interested? Reply "unsubscribe" and you won't hear from me again.</p></div>`;
const text = (h: string) => h.replace(/<br\s*\/?>/g, "\n").replace(/<\/p>/g, "\n\n").replace(/<a href="([^"]+)"[^>]*>[^<]*<\/a>/g, "$1").replace(/<[^>]+>/g, "")
  .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&middot;/g, "·").trim();
async function setting(key: string) {
  return (await db.from("irun_settings").select("value").eq("key", key).maybeSingle()).data?.value ?? null;
}
async function sentToday() {
  const since = new Date(); since.setUTCHours(0, 0, 0, 0);
  const { count } = await db.from("irun_sales_log").select("id", { count: "exact", head: true }).eq("kind", "sent").gte("created_at", since.toISOString());
  return count ?? 0;
}
async function sendNow(rows: Record<string, string>[]) {
  const [url, tok] = [await setting("calltwin_relay_url"), await setting("calltwin_relay_token")];
  if (!url || !tok) return { sent: 0, queued: rows.length, note: "Mail relay isn't set, so they'll go out on the next hourly run." };
  const cap = Number(await setting("agent_daily_cap") ?? 150);
  const room = Math.max(0, cap - (await sentToday()));
  let sent = 0, bounced = 0;
  for (const l of rows.slice(0, Math.min(room, 30))) {
    const r = await fetch(url.replace(/\/$/, "") + "/send", { method: "POST", headers: { "x-relay-token": tok, "Content-Type": "application/json" },
      body: JSON.stringify({ to: l.email, subject: l.subject, html: wrap(l.body), text: text(wrap(l.body)) }) });
    if (r.status === 422) {
      bounced++;
      await db.from("irun_sales_leads").update({ status: "bounced", error: (await r.text()).slice(0, 300) }).eq("email", l.email);
      await db.from("irun_suppress").upsert({ email: l.email, reason: "refused" });
      continue;
    }
    if (!r.ok) break;
    const mid = (await r.json().catch(() => ({})))?.messageId ?? null;
    await db.from("irun_sales_leads").update({ status: "sent", sends: 1, last_sent_at: new Date().toISOString(), last_subject: l.subject, message_id: mid, error: null }).eq("email", l.email);
    await db.from("irun_sales_log").insert({ kind: "sent", email: l.email, detail: `[agent:${l.product}] ${l.subject}`.slice(0, 2000) });
    sent++;
    await new Promise((res) => setTimeout(res, 1500));
  }
  return { sent, bounced, queued: rows.length - sent - bounced, cap, room };
}

// ---------------------------------------------------------------- api
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  let b: Record<string, any>;
  try { b = await req.json(); } catch { return json({ error: "Send JSON." }, 400); }
  if (!b.owner || b.owner !== (await setting("owner_key"))) return json({ error: "Owner key needed. Add it in iRun > Studio > Settings." }, 401);
  const app = b.app === "custom" && b.seller ? customApp(b.seller) : APPS.find((x) => x.id === b.app);
  try {
    switch (b.a) {
      case "apps":
        return json({ apps: APPS.map(({ id, name, who, hook, link }) => ({ id, name, who, hook, link })), groq: !!GROQ });
      case "find": {
        if (!app) return json({ error: "Pick an app." }, 400);
        if (app.id === "investor") return json({ error: "Investors don't publish on the map. Paste their emails in “Add your own list”." }, 400);
        const limit = Math.min(Math.max(Number(b.limit) || 25, 1), 60);
        const { leads, label, scanned } = await findLeads(app, String(b.ask ?? ""), String(b.where || "Vineland, NJ"), limit);
        const campaign = `${app.id}:${String(b.ask || app.who).slice(0, 40)}:${label}`.slice(0, 120);
        const rows = [];
        for (const [i, l] of leads.entries()) {
          const d = draft(app, l);
          const p = i < 25 ? await polish(app, l, d) : d;
          rows.push({ ...l, source: "agent", status: "draft", product: app.id, campaign, ...d, subject: p.subject, body: p.body });
        }
        if (rows.length) await db.from("irun_sales_leads").upsert(rows, { onConflict: "email", ignoreDuplicates: true });
        return json({ campaign, label, scanned, leads: rows });
      }
      case "site": {
        const url = String(b.url ?? "").trim();
        if (!url) return json({ error: "Paste a website address." }, 400);
        return json(await readSite(url));
      }
      case "enrich": {
        const leads = (b.leads ?? []).slice(0, 10).map((l: Record<string, string>) => ({ email: String(l.email ?? "").toLowerCase(), business: String(l.business ?? "").slice(0, 120), website: String(l.website ?? "") }));
        return json({ why: await whyNow(b.seller ?? null, leads) });
      }
      case "scrape": {
        // The page finds businesses on the map in the browser, then asks us for the emails on their websites.
        const sites: string[] = (b.sites ?? []).slice(0, 40);
        const out: Record<string, string | null> = {};
        for (let i = 0; i < sites.length; i += 10) {
          const got = await Promise.all(sites.slice(i, i + 10).map(async (s) => [s, await siteEmail(s)] as const));
          for (const [s, e] of got) out[s] = e;
        }
        return json({ emails: out });
      }
      case "add": {
        if (!app) return json({ error: "Pick an app." }, 400);
        const campaign = String(b.campaign || `${app.id}:own list`).slice(0, 120);
        const rows = (b.rows ?? []).map((r: Record<string, string>) => ({ ...r, email: String(r.email ?? "").trim().toLowerCase() }))
          .filter((r: Record<string, string>) => EMAIL.test(r.email)).slice(0, 500)
          .map((r: Record<string, string>) => {
            const l = { business: (r.business || r.contact || r.email.split("@")[1].split(".")[0]).slice(0, 120), contact: r.contact || null, city: r.city || null, note: r.note || null, website: r.website || null, why: r.why ? String(r.why).slice(0, 200) : null };
            const geo = { why_now: l.why, lat: Number.isFinite(+r.lat) && r.lat !== "" ? +r.lat : null, lon: Number.isFinite(+r.lon) && r.lon !== "" ? +r.lon : null, distance_mi: Number.isFinite(+r.distance_mi) && r.distance_mi !== "" ? +r.distance_mi : null };
            const { why: _w, ...lead } = l;
            return { email: r.email, ...lead, ...geo, trade: r.trade || app.who, state: r.state || null, source: b.source === "agent" ? "agent" : "own list", status: "draft", product: app.id, campaign, ...draft(app, l) };
          });
        const sup = new Set(rows.length ? ((await db.from("irun_suppress").select("email").in("email", rows.map((r: any) => r.email))).data ?? []).map((r) => r.email) : []);
        for (let i = rows.length - 1; i >= 0; i--) if (sup.has(rows[i].email)) rows.splice(i, 1);
        for (const [i, r] of rows.entries()) if (i < 25 && b.source === "agent") Object.assign(r, await polish(app, r, r));
        if (rows.length) await db.from("irun_sales_leads").upsert(rows, { onConflict: "email", ignoreDuplicates: true });
        return json({ campaign, added: rows.length, leads: rows });
      }
      case "list": {
        let q = db.from("irun_sales_leads").select("email,business,contact,trade,city,state,website,why_now,lat,lon,distance_mi,status,product,campaign,subject,body,followup_body,sends,last_sent_at,replied_at,last_reply,created_at").order("created_at", { ascending: false }).limit(500);
        if (b.status) q = q.in("status", String(b.status).split(","));
        if (b.campaign) q = q.eq("campaign", b.campaign);
        const { data, error } = await q;
        if (error) throw error;
        const all = (await db.from("irun_sales_leads").select("status,campaign").limit(20000)).data ?? [];
        const counts: Record<string, number> = {};
        const campaigns: Record<string, number> = {};
        for (const r of all) { counts[r.status] = (counts[r.status] ?? 0) + 1; if (r.campaign) campaigns[r.campaign] = (campaigns[r.campaign] ?? 0) + 1; }
        return json({ rows: data, counts, campaigns, sent_today: await sentToday(), cap: Number(await setting("agent_daily_cap") ?? 150) });
      }
      case "edit": {
        const f: Record<string, string> = {};
        for (const k of ["subject", "body", "followup_body"]) if (typeof b[k] === "string") f[k] = b[k];
        await db.from("irun_sales_leads").update(f).eq("email", String(b.email).toLowerCase()).in("status", ["draft", "approved"]);
        return json({ ok: true });
      }
      case "approve": {
        const emails = (b.emails ?? []).map((e: string) => String(e).toLowerCase()).slice(0, 500);
        const { data } = await db.from("irun_sales_leads").update({ status: "approved", approved_at: new Date().toISOString() }).in("email", emails).eq("status", "draft").select("email,subject,body,product");
        return json({ approved: data?.length ?? 0, ...(await sendNow(data ?? [])) });
      }
      case "reject": {
        const emails = (b.emails ?? []).map((e: string) => String(e).toLowerCase()).slice(0, 500);
        const { data } = await db.from("irun_sales_leads").update({ status: "skipped" }).in("email", emails).in("status", ["draft", "approved"]).select("email");
        return json({ rejected: data?.length ?? 0 });
      }
      default:
        return json({ error: "Unknown action." }, 400);
    }
  } catch (e) {
    return json({ error: (e as Error).message ?? String(e) }, 500);
  }
});
