/* HSW365 Join — one-step sign up + plan + payment for any HSW365 app.
   Visitors see the app, then join right on top of it: email, password, plan, Cash App or Zelle, one button.
   Accounts are created confirmed (no email to click), payment claims open access right away (3-day grace)
   and the owner confirms them in the HSW365 payments console.

   <script src="https://hsw365.github.io/iRUN/join/hsw-join.js"></script>
   <script>
     HSWJoin.init({ app: "flipit", name: "FLIPIT", accent: "#34d399", tagline: "Run every flip from one workspace.",
                    defaultPlan: "pro", onChange: (s) => { ...s.active, s.plan... } });
     HSWJoin.require()      // true when the member is active, otherwise opens the join sheet and returns false
     HSWJoin.open("team")   // open the sheet with a plan picked
   </script>
   ?signup or #signup in the URL opens the sheet a moment after the app shows. */
(function () {
  const SB = "https://lsxdlmrjrcivxwgfkpop.supabase.co";
  const KEY = "sb_publishable_J5jD9bSIjoKEwyR5b5S4oQ_B4RQYo9T";
  const FN = SB + "/functions/v1/hsw-join";
  const CASHTAG = "$hsw365", ZELLE = "856-796-8081";
  let cfg = {}, plans = [], sess = null, state = { active: false }, plan = null, method = "cashapp", mode = "up", root = null;
  const listeners = [];
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  const skey = () => "hswjoin:" + cfg.app;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => "$" + (Number.isInteger(n) ? n : n.toFixed(2));

  async function call(body, auth) {
    const h = { "content-type": "application/json" };
    if (auth && sess) h.authorization = "Bearer " + sess.access_token;
    const r = await fetch(FN, { method: "POST", headers: h, body: JSON.stringify({ app: cfg.app, ...body }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error) throw new Error(j.error || "Something went wrong. Try again.");
    return j;
  }
  async function token(grant, body) {
    const r = await fetch(SB + "/auth/v1/token?grant_type=" + grant, { method: "POST", headers: { "content-type": "application/json", apikey: KEY }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error_description || j.msg || "Wrong email or password.");
    return { access_token: j.access_token, refresh_token: j.refresh_token, expires_at: Date.now() + (j.expires_in || 3600) * 1000, email: j.user && j.user.email };
  }
  async function fresh() {
    if (!sess) return null;
    if (sess.expires_at - Date.now() > 60000) return sess;
    try { sess = await token("refresh_token", { refresh_token: sess.refresh_token }); store.set(skey(), sess); }
    catch { sess = null; store.set(skey(), null); }
    return sess;
  }
  function emit() { listeners.forEach((f) => { try { f(state); } catch (e) { console.error(e); } }); paintBadge(); }
  async function refresh() {
    if (!(await fresh())) { state = { active: false, signedIn: false }; return emit(), state; }
    try { state = { ...(await call({ a: "status" }, true)), signedIn: true }; }
    catch { state = { active: false, signedIn: true, email: sess.email }; }
    emit(); return state;
  }

  /* ---------- UI ---------- */
  function css(a) {
    return `@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=Inter:wght@400;500;600&family=Space+Mono:wght@700&display=swap');
.hj{position:fixed;inset:0;z-index:2147483000;display:none;align-items:center;justify-content:center;padding:16px;background:rgba(5,5,9,.62);backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);font-family:Inter,system-ui,sans-serif;color:#ecebf2}
.hj.on{display:flex}
.hj *{box-sizing:border-box}
.hj .bx{width:100%;max-width:470px;max-height:94vh;overflow:auto;background:linear-gradient(180deg,#16161f,#0e0e15);border:1px solid #33333f;border-radius:18px;padding:26px;position:relative;box-shadow:0 50px 120px -30px rgba(0,0,0,.9),0 0 0 1px ${a}22 inset}
.hj .ey{font:700 10.5px/1 'Space Mono',monospace;letter-spacing:.18em;text-transform:uppercase;color:${a}}
.hj h3{font:800 34px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;margin:8px 0 4px;letter-spacing:.01em}
.hj h3 b{color:${a};font-weight:800}
.hj .tl{font-size:14px;color:#a9a8b6;margin:0 0 16px}
.hj .x{position:absolute;top:12px;right:14px;background:none;border:0;color:#8d8c9c;font-size:24px;cursor:pointer;line-height:1}
.hj .st{display:flex;flex-direction:column;gap:11px}
.hj .tb{display:flex;border:1px solid #33333f;border-radius:9px;overflow:hidden}
.hj .tb button{flex:1;padding:11px 6px;background:none;border:0;color:#8d8c9c;font:800 13px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.08em;text-transform:uppercase;cursor:pointer}
.hj .tb button small{display:block;font:700 10px 'Space Mono',monospace;letter-spacing:.04em;margin-top:4px;opacity:.85}
.hj .tb button.on{background:${a};color:#06080c}
.hj .two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:430px){.hj .two{grid-template-columns:1fr}.hj h3{font-size:30px}}
.hj label{display:block;font:700 10px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:#8d8c9c;margin-bottom:6px}
.hj input{width:100%;background:#0a0a0f;border:1px solid #33333f;border-radius:9px;color:#ecebf2;padding:12px 13px;font:15px Inter,sans-serif;outline:none}
.hj input:focus{border-color:${a}}
.hj .py{border:1px solid #33333f;border-radius:10px;padding:13px;font-size:14px;line-height:1.5;color:#cfcfdc}
.hj .py b{font-family:'Space Mono',monospace;color:#fff}
.hj .go{border:0;border-radius:10px;padding:16px;background:${a};color:#06080c;font:800 17px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;text-transform:uppercase;cursor:pointer;box-shadow:0 14px 40px -14px ${a}}
.hj .go[disabled]{opacity:.5;pointer-events:none}
.hj .er{color:#f87171;font-size:13px;min-height:1px}
.hj .ok{color:#34d399}
.hj .al{font-size:13px;color:#8d8c9c;text-align:center}.hj .al a{color:#ecebf2;cursor:pointer;text-decoration:underline}
.hj .fine{font-size:11.5px;color:#6f6e7c;text-align:center}
.hjb{position:fixed;right:14px;bottom:14px;z-index:2147482999;display:none;font:700 11px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;padding:9px 12px;border-radius:999px;border:1px solid ${a};color:${a};background:rgba(10,10,15,.92);cursor:pointer}`;
  }
  function build() {
    const st = document.createElement("style"); st.textContent = css(cfg.accent || "#22d3ee"); document.head.appendChild(st);
    root = document.createElement("div"); root.className = "hj"; root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true");
    root.innerHTML = `<div class="bx"><button class="x" aria-label="Close">&times;</button>
      <div class="ey" id="hjEy">Start in one step</div>
      <h3 id="hjT"></h3><p class="tl" id="hjTl"></p>
      <div class="st">
        <div class="tb" id="hjPl"></div>
        <div class="two"><div><label>Email</label><input id="hjE" type="email" autocomplete="email" placeholder="you@email.com"></div>
        <div><label>Password</label><input id="hjP" type="password" autocomplete="new-password" placeholder="8+ characters"></div></div>
        <div id="hjPay"><div class="tb" id="hjM"><button data-m="cashapp" class="on">Cash App</button><button data-m="zelle">Zelle</button></div>
          <div class="py" id="hjI" style="margin-top:10px"></div>
          <div style="margin-top:10px"><label id="hjRl">Your $cashtag</label><input id="hjR" placeholder="$yourcashtag"></div></div>
        <div class="er" id="hjEr"></div>
        <button class="go" id="hjGo"></button>
        <div class="al" id="hjAl"></div>
        <div class="fine">Access opens right away. We confirm your payment the same day.</div>
      </div></div>`;
    document.body.appendChild(root);
    const $ = (s) => root.querySelector(s);
    $(".x").onclick = close;
    root.addEventListener("click", (e) => { if (e.target === root) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && root.classList.contains("on")) close(); });
    $("#hjM").onclick = (e) => { const b = e.target.closest("button"); if (b) { method = b.dataset.m; paint(); } };
    $("#hjPl").onclick = (e) => { const b = e.target.closest("button"); if (b) { plan = b.dataset.p; paint(); } };
    $("#hjAl").onclick = (e) => { if (e.target.tagName === "A") { e.preventDefault(); mode = mode === "up" ? "in" : "up"; paint(); } };
    $("#hjGo").onclick = go;
    root.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") go(); });
    const bd = document.createElement("button"); bd.className = "hjb"; bd.id = "hjBadge"; bd.onclick = () => open(); document.body.appendChild(bd);
  }
  function paint() {
    if (!root) return;
    const $ = (s) => root.querySelector(s);
    const p = plans.find((x) => x.id === plan) || plans[0] || { name: "", price: 0 };
    const signedIn = !!sess, upgrade = signedIn && !state.active;
    const nm = esc(cfg.name || "").replace(/(\d+|[A-Z]{2,}\b)$/, "<b>$1</b>");
    $("#hjT").innerHTML = mode === "in" && !signedIn ? "Welcome <b>back</b>" : upgrade ? "Unlock " + nm : "Join " + nm;
    $("#hjTl").textContent = mode === "in" && !signedIn ? "Sign in to pick up where you left off." : cfg.tagline || "";
    $("#hjPl").innerHTML = plans.map((x) => `<button data-p="${x.id}" class="${x.id === plan ? "on" : ""}">${esc(x.name)}<small>${money(x.price)}${x.per === "once" ? " once" : "/mo"}</small></button>`).join("");
    $("#hjPl").style.display = mode === "in" && !signedIn ? "none" : "";
    root.querySelectorAll("#hjM button").forEach((b) => b.classList.toggle("on", b.dataset.m === method));
    $("#hjPay").style.display = mode === "in" && !signedIn ? "none" : "";
    $("#hjI").innerHTML = `Send <b>${money(p.price)}</b> to ${method === "cashapp" ? `Cash App <b>${CASHTAG}</b> <a href="https://cash.app/${CASHTAG}/${p.price}" target="_blank" rel="noopener" style="color:inherit">open</a>` : `Zelle <b>${ZELLE}</b>`} with your email in the note.`;
    $("#hjRl").textContent = method === "cashapp" ? "Your $cashtag" : "Name on your Zelle account";
    $("#hjR").placeholder = method === "cashapp" ? "$yourcashtag" : "First Last";
    const two = root.querySelector(".two"); two.style.display = signedIn ? "none" : "";
    $("#hjE").autocomplete = "email"; $("#hjP").autocomplete = mode === "in" ? "current-password" : "new-password";
    $("#hjGo").textContent = mode === "in" && !signedIn ? "Sign in" : signedIn ? `I sent ${money(p.price)} · unlock ${p.name}` : `Create account & unlock ${p.name}`;
    $("#hjAl").innerHTML = signedIn ? "" : mode === "in" ? `New here? <a href="#">Create an account</a>` : `Already a member? <a href="#">Sign in</a>`;
  }
  function paintBadge() {
    const b = document.getElementById("hjBadge"); if (!b) return;
    if (cfg.badge === false) return;
    b.style.display = state.active ? "none" : "block";
    b.textContent = state.signedIn ? "Unlock " + (cfg.name || "") : "Join " + (cfg.name || "");
  }
  function open(p) {
    if (!root) return;
    if (p && plans.some((x) => x.id === p)) plan = p;
    if (sess && state.active) return;
    root.querySelector("#hjEr").textContent = "";
    paint(); root.classList.add("on");
    setTimeout(() => { const i = root.querySelector(sess ? "#hjR" : "#hjE"); if (i) i.focus({ preventScroll: true }); }, 120);
  }
  function close() { root && root.classList.remove("on"); }
  async function go() {
    const $ = (s) => root.querySelector(s), er = $("#hjEr"), btn = $("#hjGo");
    er.textContent = "";
    const email = $("#hjE").value.trim(), password = $("#hjP").value, ref = $("#hjR").value.trim();
    if (!sess) {
      if (!/^\S+@\S+\.\S+$/.test(email)) return (er.textContent = "Enter a valid email.");
      if (password.length < 8) return (er.textContent = "Password needs 8+ characters.");
    }
    if (!(mode === "in" && !sess) && ref.length < 2) return (er.textContent = method === "cashapp" ? "Add your $cashtag so we can match your payment." : "Add the name on your Zelle account.");
    btn.disabled = true;
    try {
      if (!sess) {
        let existed = false;
        if (mode === "up") existed = !!(await call({ a: "signup", email, password })).exists;
        try { sess = await token("password", { email, password }); }
        catch (e) { throw new Error(existed ? "That email already has an account. Check the password or tap Sign in." : e.message); }
        store.set(skey(), sess);
        await refresh();
        if (state.active) { close(); toast("Welcome back."); return; }
        if (mode === "in") { mode = "up"; paint(); btn.disabled = false; return; }
      }
      state = { ...(await call({ a: "claim", plan, method, ref }, true)), signedIn: true };
      emit(); close();
      toast("You're in. " + ((plans.find((x) => x.id === plan) || {}).name || "") + " is active.");
    } catch (e) { er.textContent = e.message; }
    finally { btn.disabled = false; paint(); }
  }
  function toast(m) {
    const t = document.createElement("div");
    t.textContent = m;
    t.style.cssText = `position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:2147483001;background:#13131c;border:1px solid ${cfg.accent || "#22d3ee"};color:#ecebf2;padding:12px 18px;border-radius:10px;font:600 14px Inter,sans-serif;box-shadow:0 20px 50px -20px #000`;
    document.body.appendChild(t); setTimeout(() => t.remove(), 3600);
  }

  async function init(c) {
    cfg = c || {}; if (c.onChange) listeners.push(c.onChange);
    sess = store.get(skey());
    const ready = () => new Promise((r) => (document.body ? r() : document.addEventListener("DOMContentLoaded", r)));
    await ready();
    build();
    try { plans = (await call({ a: "plans" })).plans; } catch { plans = c.plans || []; }
    plan = plans.some((x) => x.id === c.defaultPlan) ? c.defaultPlan : (plans[1] || plans[0] || {}).id;
    await refresh();
    if (/[?&]signup/.test(location.search) || /^#(signup|join)$/.test(location.hash)) {
      history.replaceState(null, "", location.pathname);
      if (!state.active) setTimeout(() => open(), 900);
    }
    return state;
  }
  function signOut() { sess = null; store.set(skey(), null); state = { active: false, signedIn: false }; emit(); }
  window.HSWJoin = {
    init, open, close, refresh, signOut,
    get state() { return state; },
    require() { if (state.active) return true; open(); return false; },
  };
})();
