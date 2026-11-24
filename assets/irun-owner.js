/* iRun owner session helper. Pairs with owner-login.js (HSW365 Owner Login v3): the owner signs in with the PIN only.
 * Pages use it to send the signed owner token to iRun's server functions, which re-check it with the owner-pin
 * service before granting anything. The browser flag alone only changes what the page shows.
 *   IRUN_OWNER.isOwner()    true while the PIN session is on (display only; servers verify the token)
 *   IRUN_OWNER.token()      the signed owner token, or null
 *   IRUN_OWNER.key()        the owner key saved in Studio Settings (older sign-in), or ""
 *   IRUN_OWNER.signedIn()   true with either the PIN session or a saved owner key
 *   IRUN_OWNER.body(obj)    obj plus {owner, owner_token} for owner-only API calls
 *   IRUN_OWNER.headers(h)   h plus {"X-HSW-Owner": token} while the PIN session is on
 *   IRUN_OWNER.ready()      Promise<boolean>, settles once the saved PIN session has been re-checked
 *   IRUN_OWNER.on(fn)       fn(isOwner) once ready, then again on every sign-in and sign-out
 *   IRUN_OWNER.open()       opens the PIN sign-in
 * Markup: [data-hsw-vip] shows only for the owner, [data-hsw-paywall] hides for the owner, .irun-vip is the badge.
 */
(function () {
  if (window.IRUN_OWNER) return;

  var css = document.createElement("style");
  css.textContent =
    "html:not(.hsw-owner) [data-hsw-vip]{display:none!important}html.hsw-owner [data-hsw-paywall]{display:none!important}" +
    ".irun-vip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;border:1px solid rgba(74,222,128,.5);background:rgba(22,163,74,.14);color:#4ade80;font:700 11px/1.5 'Space Mono',ui-monospace,Menlo,monospace;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;vertical-align:middle}" +
    ".irun-vip::before{content:'';width:7px;height:7px;border-radius:50%;background:#4ade80;box-shadow:0 0 8px #4ade80}" +
    ".irun-vip-note{margin:10px 0 0;padding:12px 14px;border-radius:12px;border:1px solid rgba(74,222,128,.35);background:rgba(22,163,74,.1);color:#d1fae5;font-size:14px;line-height:1.5}" +
    ".irun-vip-note b{color:#4ade80}";
  (document.head || document.documentElement).appendChild(css);

  // iRun's red owner tab. The shared owner-login.js stays unforked; this restyles its tab. It is added after that
  // script's own styles (deferred scripts run before DOMContentLoaded) and uses higher specificity.
  function tabStyle() {
    if (document.getElementById("irun-owner-tab-css")) return;
    var t = document.createElement("style"); t.id = "irun-owner-tab-css";
    t.textContent =
      "html .hswo-tab{border-radius:6px;border:1px solid #ff6673;background:#e11d2e;font-weight:800;font-size:12px;letter-spacing:.055em;text-transform:uppercase;box-shadow:0 8px 28px rgba(225,29,46,.35)}" +
      "html .hswo-tab:hover{border-color:#ff8791;background:#b91c2c}" +
      "html.hsw-owner body .hswo-tab{border-color:#22c55e;background:rgba(22,163,74,.92);box-shadow:0 8px 28px rgba(22,163,74,.3)}" +
      "html.hsw-owner body .hswo-tab:hover{background:#16a34a}";
    (document.head || document.documentElement).appendChild(t);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tabStyle); else tabStyle();

  function key() { try { return localStorage.getItem("irun_owner") || ""; } catch (e) { return ""; } }
  function isOwner() { return window.HSW_OWNER === true && !!window.HSW_OWNER_TOKEN; }
  function token() { return isOwner() ? String(window.HSW_OWNER_TOKEN) : null; }

  var readyP = null;
  function ready() {
    if (readyP) return readyP;
    readyP = new Promise(function (resolve) {
      var done = false;
      function settle() {
        if (done) return; done = true;
        var r = window.HSW_OWNER_READY;
        if (r && typeof r.then === "function") r.then(function () { resolve(isOwner()); }, function () { resolve(isOwner()); });
        else resolve(isOwner());
      }
      // owner-login.js is deferred: it runs after parsing, before DOMContentLoaded, and sets HSW_OWNER_READY.
      if (window.HSW_OWNER_READY || document.readyState === "complete") settle();
      else { document.addEventListener("DOMContentLoaded", settle); window.addEventListener("load", settle); }
    });
    return readyP;
  }

  function on(fn) {
    if (typeof fn !== "function") return;
    var last = null;
    function call(v) { v = !!v; if (v === last) return; last = v; try { fn(v); } catch (e) { console.error(e); } }
    ready().then(function () { call(isOwner()); });
    window.addEventListener("hsw-owner", function (e) { ready().then(function () { call(e && e.detail ? e.detail.owner : isOwner()); }); });
  }

  window.IRUN_OWNER = {
    isOwner: isOwner,
    token: token,
    key: key,
    signedIn: function () { return isOwner() || !!key(); },
    body: function (o) {
      var b = {}, k;
      for (k in o || {}) if (Object.prototype.hasOwnProperty.call(o, k)) b[k] = o[k];
      if (!("owner" in b)) b.owner = key() || null;
      var t = token(); if (t) b.owner_token = t;
      return b;
    },
    headers: function (h) {
      var o = {}, k;
      for (k in h || {}) if (Object.prototype.hasOwnProperty.call(h, k)) o[k] = h[k];
      var t = token(); if (t) o["X-HSW-Owner"] = t;
      return o;
    },
    ready: ready,
    on: on,
    open: function () {
      if (typeof window.HSW_OWNER_OPEN === "function") window.HSW_OWNER_OPEN();
      else if (window.hswOwner && window.hswOwner.open) window.hswOwner.open();
    }
  };
})();
