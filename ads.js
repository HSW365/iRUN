/* iRun Ads — brand kits, static ad sets in every size and 30+ languages, app/website showcase videos,
   and competitor ad tracking. Runs in the browser; uses the same free writer / Claude key as the rest of Studio. */
(function () {
  const LANGS = ["English","Spanish","Portuguese","French","German","Italian","Dutch","Polish","Romanian","Swedish","Norwegian","Danish","Finnish","Greek","Turkish","Russian","Ukrainian","Arabic","Hebrew","Hindi","Bengali","Urdu","Indonesian","Malay","Filipino (Tagalog)","Vietnamese","Thai","Chinese (Simplified)","Chinese (Traditional)","Japanese","Korean","Swahili","Haitian Creole"];
  const SIZES = [
    {id: "sq", label: "Feed 1:1", w: 1080, h: 1080},
    {id: "pt", label: "Portrait 4:5", w: 1080, h: 1350},
    {id: "st", label: "Story / Reel 9:16", w: 1080, h: 1920},
    {id: "ls", label: "Landscape 1.91:1", w: 1200, h: 628}
  ];
  const FONTS = [
    {id: "Barlow Condensed", w: 800, label: "Barlow Condensed (bold, tight)"},
    {id: "Anton", w: 400, label: "Anton (heavy poster)"},
    {id: "Bebas Neue", w: 400, label: "Bebas Neue (all caps)"},
    {id: "Montserrat", w: 800, label: "Montserrat (clean)"},
    {id: "Playfair Display", w: 800, label: "Playfair Display (luxury serif)"},
    {id: "Inter", w: 700, label: "Inter (modern)"}
  ];
  const LAYOUTS = ["bold", "photo", "split", "frame"];
  const KITS_KEY = "kits", ACTIVE_KEY = "kit_active", COMP_KEY = "competitors";

  /* ---------- markup ---------- */
  const nav = document.querySelector("nav"), promoBtn = nav.querySelector('[data-v="promo"]');
  const btn = document.createElement("button"); btn.dataset.v = "ads"; btn.textContent = "Ads";
  nav.insertBefore(btn, promoBtn ? promoBtn.nextSibling : nav.querySelector('[data-v="today"]'));
  const css = document.createElement("style");
  css.textContent = `
.kitrow{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.kitrow input[type=color]{height:46px;padding:4px}
.logoprev{width:64px;height:64px;border-radius:12px;border:1px solid var(--line);background:#0d0d14 center/contain no-repeat;flex:0 0 64px}
.sizes{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}.sizes label{display:flex;align-items:center;gap:6px;margin:0;background:#0d0d14;border:1px solid var(--line);border-radius:999px;padding:8px 12px;color:var(--text);font-size:13px;cursor:pointer}.sizes input{width:auto}
.adgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:12px}
.ad{background:var(--panel2);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.ad img{width:100%;display:block;background:#000}.ad .b{padding:10px;display:flex;flex-direction:column;gap:6px;flex:1}
.ad .t{font-size:13px;font-weight:700}.ad .s{font-size:12px;color:var(--muted)}
.comp{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line)}.comp:last-child{border:0}
.comp .btns{margin:0}
.btn.sm{padding:8px 12px;font-size:13px}
@media(max-width:560px){.kitrow{grid-template-columns:1fr 1fr}}`;
  document.head.appendChild(css);
  const opt = (arr, f) => arr.map(f).join("");
  const sec = document.createElement("section"); sec.id = "v-ads"; sec.hidden = true;
  sec.innerHTML = `
  <div class="card">
    <h2>Brand kit</h2>
    <p class="note">Your colors, font, logo and call to action. Every ad and showcase video uses the active kit so it stays on brand. Save as many kits as you have brands or clients.</p>
    <div class="row"><div><label>Kit</label><select id="kSel"></select></div><div><label>Brand name</label><input id="kName" placeholder="HSW365 Media"></div></div>
    <div class="row"><div><label>Handle</label><input id="kHandle" placeholder="hsw365media"></div><div><label>Website</label><input id="kSite" placeholder="hsw365.co"></div></div>
    <div class="kitrow">
      <div><label>Background</label><input id="kBg" type="color" value="#0a0a0f"></div>
      <div><label>Main color</label><input id="kMain" type="color" value="#22d3ee"></div>
      <div><label>Accent</label><input id="kAcc" type="color" value="#a855f7"></div>
    </div>
    <div class="row"><div><label>Headline font</label><select id="kFont">${opt(FONTS, f => `<option value="${f.id}">${f.label}</option>`)}</select></div>
      <div><label>Logo (PNG with transparent background is best)</label><div style="display:flex;gap:10px;align-items:center"><div class="logoprev" id="kLogoPrev"></div><input id="kLogo" type="file" accept="image/*"></div></div></div>
    <div class="btns"><button class="btn" id="kSave">Save kit</button><button class="btn ghost" id="kNew">New kit</button><button class="btn ghost" id="kDel">Delete kit</button><button class="btn ghost" id="kClearLogo">Remove logo</button></div>
    <div class="status" id="kStatus"></div>
  </div>

  <div class="card">
    <h2>Static ads</h2>
    <p class="note">Writes a set of ad concepts and renders every one in each size you pick, ready for Feed, Stories, Reels and link posts. Pick a language to localize the whole set.</p>
    <div class="row"><div><label>App to promote</label><select id="aProduct"></select></div><div><label>Language</label><select id="aLang">${opt(LANGS, l => `<option>${l}</option>`)}</select></div></div>
    <div class="row"><div><label>How many concepts</label><select id="aCount"><option>4</option><option selected>6</option><option>8</option><option>12</option></select></div><div><label>Angle (optional)</label><input id="aAngle" placeholder="Leave blank to mix angles"></div></div>
    <label>Sizes</label><div class="sizes">${opt(SIZES, s => `<label><input type="checkbox" value="${s.id}"${s.id === "sq" || s.id === "st" ? " checked" : ""}> ${s.label}</label>`)}</div>
    <label>Product photo or screenshot (optional, used in photo layouts)</label><input id="aImg" type="file" accept="image/*">
    <label class="chk"><input type="checkbox" id="aAI" checked> Make an AI background picture for each concept when there's no photo</label>
    <div class="btns"><button class="btn" id="aGo">Make ad set</button><button class="btn ghost" id="aAll" hidden>Download all</button></div>
    <div class="bar"><i id="aBar"></i></div>
    <div class="status" id="aStatus"></div>
    <div class="adgrid" id="aOut"></div>
  </div>

  <div class="card">
    <h2>App / website showcase video</h2>
    <p class="note">Shows your real app or site inside a phone with on-screen selling points and an end card. Add a full-page screenshot (scrolls top to bottom), several screenshots, or a screen recording from your phone.</p>
    <div class="row"><div><label>App to promote</label><select id="sProduct"></select></div><div><label>Language</label><select id="sLang">${opt(LANGS, l => `<option>${l}</option>`)}</select></div></div>
    <label>Screenshots or a screen recording</label><input id="sFiles" type="file" accept="image/*,video/*" multiple>
    <div class="note" id="sFilesNote" style="margin-top:6px"></div>
    <label>On-screen lines (one per line, 2-6 words each)</label><textarea id="sLines" placeholder="Tap Write lines, or type your own"></textarea>
    <label>Post caption</label><textarea id="sCaption"></textarea>
    <label class="chk"><input type="checkbox" id="sBeat" checked> Background beat</label>
    <div class="btns"><button class="btn ghost" id="sWrite">Write lines</button><button class="btn cy" id="sRender">Render showcase</button></div>
    <div class="bar"><i id="sBar"></i></div>
    <div class="status" id="sStatus"></div>
  </div>
  <div class="out" id="sOut"></div>

  <div class="card">
    <h2>Competitor ads</h2>
    <p class="note">Track who you're up against. Open their live ads in Meta's public Ad Library and TikTok's Top Ads, then have iRun write an ad set that answers them without naming them.</p>
    <div class="row"><div><label>Competitor name</label><input id="cName" placeholder="Brand or app name"></div><div><label>Website (optional)</label><input id="cSite" placeholder="example.com"></div></div>
    <label>What they push (optional)</label><input id="cNote" placeholder="Their main promise, offer or hook">
    <div class="btns"><button class="btn ghost" id="cAdd">Track competitor</button></div>
    <div id="cList" style="margin-top:8px"></div>
  </div>`;
  const after = document.getElementById("v-promo") || document.getElementById("v-faceless");
  after.parentNode.insertBefore(sec, after.nextSibling);

  /* ---------- helpers ---------- */
  const J = (k, d) => { try { return JSON.parse(store.get(k) || "") ?? d; } catch { return d; } };
  const lum = hex => { const n = parseInt(hex.slice(1), 16), r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255; return (0.299 * r + 0.587 * g + 0.114 * b) / 255; };
  const ink = bg => lum(bg) > 0.6 ? "#0b0b10" : "#ffffff";
  const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };
  const fontOf = k => FONTS.find(f => f.id === k.font) || FONTS[0];
  const loadImg = src => new Promise(res => { const im = new Image(); im.crossOrigin = "anonymous"; im.onload = () => res(im); im.onerror = () => res(null); im.src = src; });
  const fileUrl = f => URL.createObjectURL(f);
  function rr(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
  function fit(c, text, family, weight, maxW, maxH, maxSize, minSize, lh = 1.02, upper = true) {
    const t = upper ? String(text || "").toUpperCase() : String(text || "");
    for (let size = maxSize; size >= minSize; size -= 2) {
      c.font = `${weight} ${size}px "${family}"`;
      const lines = []; let cur = "";
      t.split(/\s+/).filter(Boolean).forEach(w => { const s = cur ? cur + " " + w : w; if (cur && c.measureText(s).width > maxW) { lines.push(cur); cur = w; } else cur = s; });
      if (cur) lines.push(cur);
      if (lines.length * size * lh <= maxH && lines.every(l => c.measureText(l).width <= maxW)) return {lines, size, lh: size * lh, font: c.font};
    }
    c.font = `${weight} ${minSize}px "${family}"`; return {lines: [t], size: minSize, lh: minSize * lh, font: c.font};
  }
  function drawLines(c, f, x, y, color, align = "left", stroke) {
    c.font = f.font; c.textAlign = align; c.textBaseline = "top"; c.fillStyle = color;
    f.lines.forEach((l, i) => { if (stroke) { c.lineJoin = "round"; c.lineWidth = stroke[1]; c.strokeStyle = stroke[0]; c.strokeText(l, x, y + i * f.lh); } c.fillText(l, x, y + i * f.lh); });
    c.textAlign = "left"; return y + f.lines.length * f.lh;
  }
  function cover(c, im, x, y, w, h, zoom = 1) {
    const s = Math.max(w / (im.videoWidth || im.width), h / (im.videoHeight || im.height)) * zoom, dw = (im.videoWidth || im.width) * s, dh = (im.videoHeight || im.height) * s;
    c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); c.drawImage(im, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh); c.restore();
  }
  function glow(c, w, h, k) {
    c.fillStyle = k.bg; c.fillRect(0, 0, w, h);
    const g = (x, y, r, col) => { const gr = c.createRadialGradient(x, y, 0, x, y, r); gr.addColorStop(0, col); gr.addColorStop(1, rgba(k.bg, 0)); c.fillStyle = gr; c.fillRect(0, 0, w, h); };
    g(w * 0.15, h * 0.2, Math.max(w, h) * 0.75, rgba(k.acc, 0.38)); g(w * 0.9, h * 0.85, Math.max(w, h) * 0.8, rgba(k.main, 0.30));
  }
  function pill(c, text, x, y, k, size, align = "left") {
    c.font = `800 ${size}px "${fontOf(k).id === "Playfair Display" ? "Montserrat" : "Barlow Condensed"}"`;
    const t = String(text || "").toUpperCase(), tw = c.measureText(t).width, ph = size * 1.7, pw = tw + size * 1.6;
    const px = align === "center" ? x - pw / 2 : x;
    c.fillStyle = k.main; rr(c, px, y, pw, ph, ph / 2); c.fill();
    c.fillStyle = ink(k.main); c.textBaseline = "middle"; c.fillText(t, px + size * 0.8, y + ph / 2 + size * 0.04); return ph;
  }
  function brandMark(c, k, logo, x, y, size, color) {
    if (logo) { const s = size / Math.max(logo.width, logo.height) * 1.6, w = logo.width * s, h = logo.height * s; c.drawImage(logo, x, y + (size - h) / 2, w, h); return; }
    c.font = `700 ${Math.round(size * 0.62)}px "Space Mono"`; c.textBaseline = "middle"; c.fillStyle = color; c.fillText(String(k.name || "@" + k.handle).toUpperCase(), x, y + size / 2);
  }

  /* ---------- brand kits ---------- */
  function defaultKit() { return {id: "k" + Date.now(), name: "HSW365 Media", handle: handle(), site: "hsw365.co", bg: "#0a0a0f", main: "#22d3ee", acc: "#a855f7", font: "Barlow Condensed", logo: ""}; }
  let kits = J(KITS_KEY, null); if (!Array.isArray(kits) || !kits.length) kits = [defaultKit()];
  let activeId = store.get(ACTIVE_KEY) || kits[0].id; if (!kits.find(k => k.id === activeId)) activeId = kits[0].id;
  const kit = () => kits.find(k => k.id === activeId) || kits[0];
  const saveKits = () => { store.set(KITS_KEY, JSON.stringify(kits)); store.set(ACTIVE_KEY, activeId); };
  function showKit() {
    const k = kit();
    $("kSel").innerHTML = opt(kits, x => `<option value="${x.id}"${x.id === k.id ? " selected" : ""}>${esc(x.name || "Untitled kit")}</option>`);
    $("kName").value = k.name; $("kHandle").value = k.handle; $("kSite").value = k.site; $("kBg").value = k.bg; $("kMain").value = k.main; $("kAcc").value = k.acc; $("kFont").value = k.font;
    $("kLogoPrev").style.backgroundImage = k.logo ? `url(${k.logo})` : "none";
  }
  function readKit() { const k = kit(); Object.assign(k, {name: $("kName").value.trim(), handle: $("kHandle").value.trim().replace(/^@/, ""), site: $("kSite").value.trim(), bg: $("kBg").value, main: $("kMain").value, acc: $("kAcc").value, font: $("kFont").value}); return k; }
  $("kSel").onchange = () => { activeId = $("kSel").value; saveKits(); showKit(); };
  $("kSave").onclick = () => { readKit(); saveKits(); showKit(); setStatus("kStatus", "Kit saved on this device.", "ok"); };
  $("kNew").onclick = () => { const k = defaultKit(); k.name = "New brand"; kits.push(k); activeId = k.id; saveKits(); showKit(); $("kName").focus(); };
  $("kDel").onclick = () => { if (kits.length < 2) { setStatus("kStatus", "Keep at least one kit.", "err"); return; } if (!confirm("Delete this kit?")) return; kits = kits.filter(k => k.id !== activeId); activeId = kits[0].id; saveKits(); showKit(); };
  $("kClearLogo").onclick = () => { kit().logo = ""; saveKits(); showKit(); };
  $("kLogo").onchange = async e => {
    const f = e.target.files[0]; if (!f) return; const im = await loadImg(fileUrl(f)); if (!im) return setStatus("kStatus", "Couldn't read that image.", "err");
    const s = Math.min(1, 360 / Math.max(im.width, im.height)), c = document.createElement("canvas"); c.width = Math.round(im.width * s); c.height = Math.round(im.height * s);
    c.getContext("2d").drawImage(im, 0, 0, c.width, c.height); kit().logo = c.toDataURL("image/png"); readKit(); saveKits(); showKit(); setStatus("kStatus", "Logo added.", "ok"); e.target.value = "";
  };

  /* ---------- AI ---------- */
  const AD_SYSTEM = `You are a senior performance-marketing copywriter. Write static social ad concepts (Meta and TikTok feed/story ads).
Rules:
- Write every word in the requested language, natural for native speakers, not a literal translation.
- headline: 2-7 words, scroll-stopping. sub: 6-16 words that explain the benefit. cta: 1-4 words.
- Each concept uses a different angle (pain point, outcome, how it works, who it's for, speed, objection).
- Only claim what the product description says. No prices unless given, no discounts, no income or results guarantees, no fake statistics, no fake testimonials, no competitor names.
- No emojis. No hashtags inside headline/sub/cta.
- visual: an English description of a photo that fits the concept, with no text, logos or real people's names.
Return ONLY JSON: {"ads":[{"headline":"","sub":"","cta":"","visual":""}],"caption":"1-2 sentence post caption in the requested language","hashtags":["..."]}`;
  const SHOW_SYSTEM = `You write the on-screen lines for a 15-second vertical app showcase video. Write in the requested language.
Return ONLY JSON: {"lines":["4 or 5 lines, each 2-6 words: hook, 2-3 key features or benefits, payoff"],"caption":"1-2 sentence post caption","hashtags":["..."]}.
Only claim what the product description says. No prices, no guarantees, no fake numbers, no emojis.`;
  const productOpts = () => opt(PRODUCTS, p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`);
  const tags = h => (h || []).slice(0, 6).map(t => "#" + String(t).replace(/^#/, "").replace(/\s/g, "")).join(" ");

  /* ---------- static ads ---------- */
  function renderAd(ad, size, layout, k, logo, pic) {
    const c = document.createElement("canvas"); c.width = size.w; c.height = size.h; const x = c.getContext("2d");
    const W2 = size.w, H2 = size.h, m = Math.round(Math.min(W2, H2) * 0.075), wide = W2 / H2 > 1.4, tall = H2 / W2 > 1.5;
    const F = fontOf(k), up = F.id !== "Playfair Display" && F.id !== "Inter" && F.id !== "Montserrat" ? true : false;
    const head = s => fit(x, ad.headline, F.id, F.w, s.w, s.h, s.max, 36, F.id === "Playfair Display" ? 1.08 : 0.98, up);
    const sub = (w, h, max) => fit(x, ad.sub, "Inter", 600, w, h, max, 22, 1.28, false);
    const mark = Math.round(Math.min(W2, H2) * 0.055), ctaSize = Math.round(Math.min(W2, H2) * (wide ? 0.045 : 0.046));
    if (layout === "photo" && !pic) layout = "bold";
    if ((layout === "split" || layout === "frame") && !pic) layout = "bold";
    if (layout === "bold") {
      glow(x, W2, H2, k);
      x.fillStyle = k.main; x.fillRect(m, m + mark + m * 0.6, Math.round(W2 * 0.12), Math.max(6, Math.round(H2 * 0.008)));
      brandMark(x, k, logo, m, m, mark, ink(k.bg));
      const hw = wide ? W2 * 0.62 : W2 - m * 2, top = tall ? H2 * 0.24 : m + mark + m * 1.3;
      const f = head({w: hw, h: (H2 - top - m) * (tall ? 0.42 : 0.5), max: Math.round(W2 * (wide ? 0.11 : tall ? 0.16 : 0.13))});
      let y = drawLines(x, f, m, top, ink(k.bg));
      const s = sub(hw, H2 * 0.2, Math.round(W2 * (wide ? 0.03 : 0.038))); y = drawLines(x, s, m, y + m * 0.5, rgba(ink(k.bg) === "#ffffff" ? "#ffffff" : "#0b0b10", 0.78));
      pill(x, ad.cta, m, Math.max(y + m * 0.7, H2 - m - ctaSize * 1.7), k, ctaSize);
    } else if (layout === "photo") {
      cover(x, pic, 0, 0, W2, H2, 1.02);
      const gr = x.createLinearGradient(0, H2 * 0.25, 0, H2); gr.addColorStop(0, rgba(k.bg, 0)); gr.addColorStop(0.55, rgba(k.bg, 0.78)); gr.addColorStop(1, rgba(k.bg, 0.96)); x.fillStyle = gr; x.fillRect(0, 0, W2, H2);
      const tg = x.createLinearGradient(0, 0, 0, m * 3); tg.addColorStop(0, rgba(k.bg, 0.6)); tg.addColorStop(1, rgba(k.bg, 0)); x.fillStyle = tg; x.fillRect(0, 0, W2, m * 3);
      brandMark(x, k, logo, m, m, mark, "#ffffff");
      const hw = wide ? W2 * 0.7 : W2 - m * 2, ch = ctaSize * 1.7;
      const s = sub(hw, H2 * 0.14, Math.round(W2 * (wide ? 0.028 : 0.036)));
      const f = head({w: hw, h: H2 * (tall ? 0.3 : 0.32), max: Math.round(W2 * (wide ? 0.09 : 0.13))});
      const blockH = f.lines.length * f.lh + m * 0.4 + s.lines.length * s.lh + m * 0.6 + ch;
      let y = H2 - m - blockH - (tall ? H2 * 0.08 : 0);
      y = drawLines(x, f, m, y, "#ffffff"); y = drawLines(x, s, m, y + m * 0.4, "rgba(255,255,255,.85)");
      pill(x, ad.cta, m, y + m * 0.6, k, ctaSize);
    } else if (layout === "split") {
      x.fillStyle = k.bg; x.fillRect(0, 0, W2, H2);
      if (wide) { cover(x, pic, W2 * 0.5, 0, W2 * 0.5, H2); }
      else { cover(x, pic, 0, 0, W2, H2 * (tall ? 0.52 : 0.5)); }
      const tx = m, tw = wide ? W2 * 0.5 - m * 2 : W2 - m * 2, ty = wide ? m + mark + m * 0.8 : H2 * (tall ? 0.52 : 0.5) + m;
      x.fillStyle = k.main; if (wide) x.fillRect(W2 * 0.5 - 6, 0, 12, H2); else x.fillRect(0, H2 * (tall ? 0.52 : 0.5) - 6, W2, 12);
      brandMark(x, k, logo, wide ? m : m, wide ? m : ty, mark, ink(k.bg));
      const top = wide ? ty : ty + mark + m * 0.6, ch = ctaSize * 1.7;
      const f = head({w: tw, h: (H2 - top - m - ch) * 0.62, max: Math.round(W2 * (wide ? 0.06 : 0.1))});
      let y = drawLines(x, f, tx, top, ink(k.bg));
      const s = sub(tw, (H2 - y - m - ch) * 0.8, Math.round(W2 * (wide ? 0.022 : 0.034))); y = drawLines(x, s, tx, y + m * 0.35, rgba(ink(k.bg), 0.78));
      pill(x, ad.cta, tx, Math.min(y + m * 0.5, H2 - m - ch), k, ctaSize);
    } else { // frame
      glow(x, W2, H2, k);
      brandMark(x, k, logo, m, m, mark, ink(k.bg));
      const hw = wide ? W2 * 0.48 : W2 - m * 2, ch = ctaSize * 1.7;
      const f = head({w: hw, h: H2 * (wide ? 0.5 : tall ? 0.2 : 0.22), max: Math.round(W2 * (wide ? 0.07 : 0.1))});
      const top = m + mark + m * 0.8; let y = drawLines(x, f, m, top, ink(k.bg));
      let fx, fy, fw, fh;
      if (wide) { fx = W2 * 0.55; fy = m; fw = W2 * 0.45 - m; fh = H2 - m * 2; const s = sub(hw, H2 * 0.22, Math.round(W2 * 0.022)); y = drawLines(x, s, m, y + m * 0.3, rgba(ink(k.bg), 0.78)); pill(x, ad.cta, m, H2 - m - ch, k, ctaSize); }
      else { fx = m; fy = y + m * 0.6; fw = W2 - m * 2; fh = H2 - fy - m * 2.2 - ch; pill(x, ad.cta, W2 / 2, H2 - m - ch, k, ctaSize, "center"); }
      x.save(); x.shadowColor = rgba("#000000", 0.45); x.shadowBlur = 50; x.shadowOffsetY = 20; x.fillStyle = k.bg; rr(x, fx, fy, fw, fh, 28); x.fill(); x.restore();
      x.save(); rr(x, fx, fy, fw, fh, 28); x.clip(); cover(x, pic, fx, fy, fw, fh); x.restore();
      x.strokeStyle = k.main; x.lineWidth = 6; rr(x, fx, fy, fw, fh, 28); x.stroke();
    }
    return c;
  }
  let lastAds = [];
  $("aGo").onclick = async () => {
    const p = prod($("aProduct").value); if (!p) return;
    const sizes = [...document.querySelectorAll("#v-ads .sizes input:checked")].map(i => SIZES.find(s => s.id === i.value));
    if (!sizes.length) return setStatus("aStatus", "Pick at least one size.", "err");
    const k = readKit(); saveKits(); $("aGo").disabled = true; $("aAll").hidden = true; $("aOut").innerHTML = ""; lastAds = []; $("aBar").style.width = "0";
    try {
      setStatus("aStatus", "Writing concepts...");
      await Promise.all(FONTS.map(f => document.fonts.load(`${f.w} 60px "${f.id}"`))); await document.fonts.load('600 30px "Inter"');
      const comp = $("aGo").dataset.comp || ""; delete $("aGo").dataset.comp;
      const n = +$("aCount").value, lang = $("aLang").value;
      const j = jsonOut(await ai(AD_SYSTEM, `Product: ${p.name}\nWhat it does: ${p.pitch}\nWho it's for: ${p.audience}\nAngle: ${$("aAngle").value.trim() || "mix of angles"}${comp ? `\nPosition against a competitor without naming them. They push: ${comp}` : ""}\nCall to action idea: DM ${p.keyword.toUpperCase()} / get the link\nLanguage: ${lang}\nNumber of concepts: ${n}`, 3000));
      const ads = (j.ads || []).filter(a => a.headline).slice(0, n);
      if (!ads.length) throw new Error("No concepts came back. Tap again.");
      const logo = k.logo ? await loadImg(k.logo) : null, upload = $("aImg").files[0] ? await loadImg(fileUrl($("aImg").files[0])) : null;
      const caption = `${j.caption || ""}\n\n${cta("instagram", p.keyword.toUpperCase()).caption}\n\n${tags(j.hashtags)}`.trim();
      const total = ads.length * sizes.length; let done = 0;
      for (let i = 0; i < ads.length; i++) {
        const ad = ads[i], layout = LAYOUTS[i % LAYOUTS.length];
        let pic = upload;
        if (!pic && $("aAI").checked && layout !== "bold") { setStatus("aStatus", `Making picture ${i + 1} of ${ads.length}...`); pic = await loadPic(picUrl(ad.visual || p.pitch, (STYLES[0] || {}).id, 1000 + i * 77)); }
        for (const sz of sizes) {
          const c = renderAd(ad, sz, layout, k, logo, pic), url = c.toDataURL("image/png"), name = `${p.id}-ad${i + 1}-${sz.id}-${lang.split(" ")[0].toLowerCase()}.png`;
          lastAds.push({url, name});
          const el = document.createElement("div"); el.className = "ad";
          el.innerHTML = `<img src="${url}" alt="${esc(ad.headline)}"><div class="b"><div class="t">${esc(ad.headline)}</div><div class="s">${esc(sz.label)} · ${esc(layout)}</div><div class="btns" style="margin-top:auto"><a class="btn ghost sm" href="${url}" download="${name}">Download</a><button class="btn ghost sm" data-cap>Copy caption</button></div></div>`;
          el.querySelector("[data-cap]").onclick = async e => { try { await navigator.clipboard.writeText(caption); e.target.textContent = "Copied"; } catch { e.target.textContent = "Copy failed"; } };
          $("aOut").appendChild(el); done++; $("aBar").style.width = (done / total * 100).toFixed(0) + "%";
          await new Promise(r => setTimeout(r, 0));
        }
      }
      $("aAll").hidden = false;
      setStatus("aStatus", `${lastAds.length} ads ready in ${lang}.`, "ok");
    } catch (e) { setStatus("aStatus", e.message, "err"); }
    $("aGo").disabled = false;
  };
  $("aAll").onclick = async () => { for (const a of lastAds) { const l = document.createElement("a"); l.href = a.url; l.download = a.name; document.body.appendChild(l); l.click(); l.remove(); await new Promise(r => setTimeout(r, 350)); } };

  /* ---------- showcase video ---------- */
  let media = [];
  $("sFiles").onchange = e => {
    media.forEach(m => URL.revokeObjectURL(m.url));
    media = [...e.target.files].map(f => ({f, url: fileUrl(f), video: f.type.startsWith("video")}));
    const v = media.filter(m => m.video).length;
    $("sFilesNote").textContent = media.length ? (v ? `Using the screen recording${media.length > 1 ? " (first video only)" : ""}.` : `${media.length} screenshot${media.length > 1 ? "s" : ""} added.`) : "";
  };
  $("sWrite").onclick = async () => {
    const p = prod($("sProduct").value); if (!p) return; $("sWrite").disabled = true; setStatus("sStatus", "Writing...");
    try {
      const j = jsonOut(await ai(SHOW_SYSTEM, `Product: ${p.name}\nWhat it does: ${p.pitch}\nWho it's for: ${p.audience}\nLanguage: ${$("sLang").value}`, 900));
      $("sLines").value = (j.lines || []).slice(0, 5).join("\n");
      $("sCaption").value = `${j.caption || ""}\n\n${cta("instagram", p.keyword.toUpperCase()).caption}\n\n${tags(j.hashtags)}`.trim();
      setStatus("sStatus", "Lines ready. Edit them, then render.", "ok");
    } catch (e) { setStatus("sStatus", e.message, "err"); }
    $("sWrite").disabled = false;
  };
  function phone(c, k, draw, t) {
    const pw = 680, ph = 1360, px = (W - pw) / 2, py = 460, r = 86, bz = 22;
    c.save(); c.shadowColor = rgba(k.main, 0.35); c.shadowBlur = 90; c.fillStyle = "#050507"; rr(c, px, py, pw, ph, r); c.fill(); c.restore();
    c.strokeStyle = "#2a2a36"; c.lineWidth = 4; rr(c, px, py, pw, ph, r); c.stroke();
    const sx = px + bz, sy = py + bz, sw = pw - bz * 2, sh = ph - bz * 2;
    c.save(); rr(c, sx, sy, sw, sh, r - bz); c.clip(); c.fillStyle = "#000"; c.fillRect(sx, sy, sw, sh); draw(sx, sy, sw, sh); c.restore();
    c.fillStyle = "#050507"; rr(c, W / 2 - 90, sy + 18, 180, 46, 23); c.fill();
  }
  $("sRender").onclick = async () => {
    const p = prod($("sProduct").value); if (!p) return;
    if (!media.length) return setStatus("sStatus", "Add a screenshot or a screen recording first.", "err");
    const lines = $("sLines").value.split("\n").map(s => s.trim()).filter(Boolean);
    if (!lines.length) return setStatus("sStatus", "Add on-screen lines, or tap Write lines.", "err");
    const k = readKit(); saveKits(); $("sRender").disabled = true; STOP = false;
    try {
      await Promise.all([document.fonts.load(`${fontOf(k).w} 100px "${fontOf(k).id}"`), document.fonts.load('700 30px "Space Mono"'), document.fonts.load('600 30px "Inter"')]);
      const ac = ctx(); await ac.resume();
      const logo = k.logo ? await loadImg(k.logo) : null;
      const vidM = media.find(m => m.video); let vid = null, imgs = [];
      if (vidM) { vid = document.createElement("video"); vid.src = vidM.url; vid.muted = true; vid.playsInline = true; await new Promise((res, rej) => { vid.onloadeddata = res; vid.onerror = () => rej(new Error("Couldn't read that recording. Use MP4 or WebM.")); }); }
      else imgs = (await Promise.all(media.map(m => loadImg(m.url)))).filter(Boolean);
      const per = 2.6, body = vid ? Math.min(Math.max(vid.duration || 12, lines.length * 2), 30) : Math.max(lines.length * per, 8), END = 3.2, total = body + END, lineDur = body / lines.length;
      const dest = ac.createMediaStreamDestination(), t0 = ac.currentTime + 0.3;
      if ($("sBeat").checked) scheduleBeat(ac, dest, t0, total, 0.45); else { const o = ac.createConstantSource(), z = ac.createGain(); z.gain.value = 0; o.connect(z).connect(dest); o.start(); o.stop(t0 + total); }
      const F = fontOf(k), up = !["Playfair Display", "Inter", "Montserrat"].includes(F.id);
      const frame = el => {
        el = Math.max(0, el);
        g2.setTransform(1, 0, 0, 1, 0, 0); glow(g2, W, H, k);
        if (el < body) {
          brandMark(g2, k, logo, 70, 120, 60, ink(k.bg));
          const li = Math.min(Math.floor(el / lineDur), lines.length - 1), lt = el - li * lineDur, a = Math.min(lt / 0.25, 1);
          g2.save(); g2.globalAlpha = a; g2.translate(0, (1 - a) * 24);
          const f = fit(g2, lines[li], F.id, F.w, W - 160, 210, 120, 50, 0.98, up); const y0 = 215 + (210 - f.lines.length * f.lh) / 2;
          f.lines.forEach((l, i) => { g2.textAlign = "center"; g2.textBaseline = "top"; g2.fillStyle = li === 0 ? k.main : ink(k.bg); g2.fillText(l, W / 2, y0 + i * f.lh); }); g2.textAlign = "left"; g2.restore();
          phone(g2, k, (sx, sy, sw, sh) => {
            if (vid) { if (vid.paused && vid.currentTime < (vid.duration || 1) - 0.1) vid.play().catch(() => {}); cover(g2, vid, sx, sy, sw, sh); return; }
            const n = imgs.length, seg = body / n, ii = Math.min(Math.floor(el / seg), n - 1), pr = Math.min((el - ii * seg) / seg, 1), im = imgs[ii];
            const s = sw / im.width, dh = im.height * s;
            if (dh > sh * 1.15) { const ease = pr < 0.12 ? 0 : Math.min((pr - 0.12) / 0.8, 1), e2 = ease * ease * (3 - 2 * ease); g2.drawImage(im, sx, sy - (dh - sh) * e2, sw, dh); }
            else cover(g2, im, sx, sy, sw, sh, 1 + 0.05 * pr);
            if (n > 1 && el - ii * seg < 0.3 && ii > 0) { g2.globalAlpha = 1 - (el - ii * seg) / 0.3; const pv = imgs[ii - 1]; cover(g2, pv, sx, sy, sw, sh); g2.globalAlpha = 1; }
          }, el);
        } else {
          const t = el - body, a = Math.min(t / 0.4, 1);
          g2.globalAlpha = a;
          if (logo) { const s = 260 / Math.max(logo.width, logo.height), w = logo.width * s, h = logo.height * s; g2.drawImage(logo, (W - w) / 2, H * 0.27 - h / 2, w, h); }
          const f = fit(g2, p.name, F.id, F.w, W - 160, 380, 200, 70, 0.98, up); const y = drawLines(g2, f, W / 2, H * 0.36, ink(k.bg), "center");
          if (k.site) { g2.font = '700 40px "Space Mono"'; g2.textAlign = "center"; g2.fillStyle = k.main; g2.fillText(k.site.toUpperCase(), W / 2, y + 40); g2.textAlign = "left"; }
          g2.globalAlpha = Math.max(0, Math.min((t - 0.4) / 0.4, 1));
          pill(g2, `DM "${p.keyword.toUpperCase()}" TO @${(k.handle || handle()).toUpperCase()}`, W / 2, H * 0.62, k, 58, "center");
          g2.globalAlpha = 1;
        }
        g2.fillStyle = rgba(ink(k.bg), 0.15); g2.fillRect(70, H - 140, W - 140, 5); g2.fillStyle = k.main; g2.fillRect(70, H - 140, (W - 140) * Math.min(el / total, 1), 5);
      };
      frame(0);
      const stream = new MediaStream([...cv.captureStream(FPS).getVideoTracks(), ...dest.stream.getAudioTracks()]), mime = pickMime();
      const rec = new MediaRecorder(stream, mime ? {mimeType: mime, videoBitsPerSecond: 10_000_000, audioBitsPerSecond: 160_000} : undefined);
      const chunks = []; rec.ondataavailable = e => e.data.size && chunks.push(e.data); const done = new Promise(r => rec.onstop = r);
      while (ac.currentTime < t0 - 0.02) await new Promise(r => setTimeout(r, 10));
      if (vid) { vid.currentTime = 0; vid.play().catch(() => {}); }
      rec.start(250); setStatus("sStatus", "Rendering... keep this tab open.");
      await new Promise(res => { const tick = () => { const el = ac.currentTime - t0; if (el >= total || STOP) return res(); frame(el); $("sBar").style.width = (el / total * 100).toFixed(0) + "%"; setTimeout(tick, 1000 / FPS); }; tick(); });
      if (vid) vid.pause(); rec.stop(); await done;
      const type = (rec.mimeType || mime || "video/webm").split(";")[0];
      const res = {blob: new Blob(chunks, {type}), ext: type.includes("mp4") ? "mp4" : "webm"};
      outCard({platform: "showcase", pill: "Showcase", product: p, caption: $("sCaption").value.trim() || `${p.pitch.split(".")[0]}.\n\n${cta("instagram", p.keyword.toUpperCase()).caption}`}, res, $("sOut"));
      $("sBar").style.width = "100%"; setStatus("sStatus", `Done (${res.ext.toUpperCase()}). Tap Share to post, or Download.`, "ok");
    } catch (e) { setStatus("sStatus", e.message, "err"); }
    $("sRender").disabled = false;
  };

  /* ---------- competitors ---------- */
  let comps = J(COMP_KEY, []); if (!Array.isArray(comps)) comps = [];
  const saveComps = () => store.set(COMP_KEY, JSON.stringify(comps));
  function showComps() {
    $("cList").innerHTML = comps.length ? comps.map((c, i) => {
      const q = encodeURIComponent(c.name);
      return `<div class="comp"><div><b>${esc(c.name)}</b>${c.site ? ` <span class="mono">${esc(c.site)}</span>` : ""}${c.note ? `<div class="note">${esc(c.note)}</div>` : ""}</div>
      <div class="btns"><a class="btn ghost sm" target="_blank" rel="noopener" href="https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q=${q}&search_type=keyword_unordered&media_type=all">Meta ads</a>
      <a class="btn ghost sm" target="_blank" rel="noopener" href="https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en">TikTok top ads</a>
      ${c.site ? `<a class="btn ghost sm" target="_blank" rel="noopener" href="${/^https?:/.test(c.site) ? esc(c.site) : "https://" + esc(c.site)}">Site</a>` : ""}
      <button class="btn sm" data-counter="${i}">Write counter-ads</button><button class="btn ghost sm" data-crm="${i}">Remove</button></div></div>`;
    }).join("") : '<p class="note">No competitors tracked yet.</p>';
    $("cList").querySelectorAll("[data-crm]").forEach(b => b.onclick = () => { comps.splice(+b.dataset.crm, 1); saveComps(); showComps(); });
    $("cList").querySelectorAll("[data-counter]").forEach(b => b.onclick = () => {
      const c = comps[+b.dataset.counter]; $("aGo").dataset.comp = c.note || `the same audience as ${c.site || "a rival product"}`;
      $("aAngle").value = "why ours is the better choice"; $("aGo").scrollIntoView({behavior: "smooth", block: "center"}); $("aGo").click();
    });
  }
  $("cAdd").onclick = () => { const name = $("cName").value.trim(); if (!name) return; comps.push({name, site: $("cSite").value.trim(), note: $("cNote").value.trim()}); saveComps(); ["cName", "cSite", "cNote"].forEach(id => $(id).value = ""); showComps(); };

  /* ---------- boot ---------- */
  btn.onclick = () => { document.querySelectorAll("nav button").forEach(x => x.classList.toggle("on", x === btn)); document.querySelectorAll("section[id^='v-']").forEach(s => s.hidden = s.id !== "v-ads"); };
  const fillProducts = () => { if (!PRODUCTS.length) return setTimeout(fillProducts, 300); $("aProduct").innerHTML = productOpts(); $("sProduct").innerHTML = productOpts(); };
  showKit(); showComps(); fillProducts();
})();
