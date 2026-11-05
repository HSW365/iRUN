"""Showcase ads: Larven-style product ads for HSW365 apps, a different composition for every app.

Each ad is a vertical 1080x1920 Reel (~15s): giant two-line headline (white + accent gradient), the app's REAL screen
captured live from its URL inside a device frame, glowing particles and light streaks, feature row with icons, the
HSW365 brand on screen the whole time, a narrator, a synth score with hits, and an end card with a QR code straight to
the app's sign-up.

Five layouts, never the same one twice in a row (state in config/showcase_state.json):
  browser  headline, browser window with the live site, a glowing button, a fan of feature cards, icon row
  phone    left-aligned headline, two phones with the live mobile site, floating stat chips
  split    full-bleed tilted desktop shot on top, numbered benefits below
  stat     one giant stat with orbit rings, the screen as a floating card, pills
  stack    cascading stacked screen cards, headline at the bottom, CTA bar

  python engine/showcase.py calltwin out/calltwin-showcase.mp4 [--layout phone]
Needs: pip install playwright segno edge-tts numpy && python -m playwright install --with-deps chromium; ffmpeg.
"""
import argparse
import asyncio
import base64
import html
import io
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CFG = os.path.join(ROOT, "config", "showcase.json")
STATE = os.path.join(ROOT, "config", "showcase_state.json")
FONTS = os.path.join(ROOT, "assets", "hsw", "fonts")
LAYOUTS = ["browser", "phone", "split", "stat", "stack"]
W, H, FPS = 1080, 1920, 30
VOICE = os.environ.get("SHOWCASE_VOICE", "en-US-AndrewMultilingualNeural")

ICONS = [  # simple line icons (24x24 viewBox)
    '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 18 9 5 9-5"/>',
    '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
]


def esc(s):
    return html.escape(str(s or ""))


# ------------------------------------------------------------------ capture the live app
async def capture(url, workdir):
    from playwright.async_api import async_playwright
    out = {}
    async with async_playwright() as p:
        proxy = {"server": os.environ["HTTPS_PROXY"]} if os.environ.get("SHOWCASE_PROXY") and os.environ.get("HTTPS_PROXY") else None
        b = await p.chromium.launch(proxy=proxy)
        for kind, vp, scale, mobile in (("desk", (1440, 900), 1, False), ("mob", (390, 844), 3, True)):
            ctx = await b.new_context(viewport={"width": vp[0], "height": vp[1]}, device_scale_factor=scale, is_mobile=mobile,
                                      color_scheme="dark", ignore_https_errors=bool(proxy))
            page = await ctx.new_page()
            path = os.path.join(workdir, f"{kind}.jpg")
            try:
                await page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                try:
                    await page.goto(url, wait_until="load", timeout=45000)
                except Exception as e:
                    print(f"[showcase] couldn't load {url} ({kind}): {e}")
            await page.wait_for_timeout(2500)
            await page.screenshot(path=path, type="jpeg", quality=88)
            out[kind] = path
            await ctx.close()
        await b.close()
    return out


def data_uri(path, mime="image/jpeg"):
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def qr_svg(url):
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=10, border=2, dark="#0a0a0f", light="#ffffff")
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------------ layouts
def head_css(a1, a2, dur):
    f = lambda n: "file://" + os.path.join(FONTS, n)
    return f"""
@font-face{{font-family:Barlow;src:url({f('barlow-condensed-latin-800-normal.woff2')});font-weight:800}}
@font-face{{font-family:Barlow;src:url({f('barlow-condensed-latin-900-normal.woff2')});font-weight:900}}
@font-face{{font-family:Inter;src:url({f('inter-latin-wght-normal.woff2')});font-weight:100 900}}
@font-face{{font-family:Mono;src:url({f('space-mono-latin-700-normal.woff2')});font-weight:700}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#06060c;color:#f4f4fa;font-family:Inter,sans-serif}}
:root{{--a1:{a1};--a2:{a2}}}
.stage{{position:absolute;inset:0;overflow:hidden;animation:push {dur}s linear both}}
@keyframes push{{from{{transform:scale(1)}}to{{transform:scale(1.045)}}}}
.bg{{position:absolute;inset:-100px;background:radial-gradient(900px 700px at 50% 38%,color-mix(in srgb,var(--a1) 28%,transparent),transparent 70%),
  radial-gradient(700px 600px at 85% 90%,color-mix(in srgb,var(--a2) 22%,transparent),transparent 70%),#06060c}}
.dots{{position:absolute;inset:0;background-image:radial-gradient(circle,rgba(255,255,255,.55) 1.2px,transparent 1.6px),
  radial-gradient(circle,color-mix(in srgb,var(--a1) 80%,white) 2px,transparent 2.6px);background-size:90px 90px,230px 230px;
  background-position:0 0,40px 70px;opacity:.35;animation:drift {dur}s linear both}}
@keyframes drift{{to{{background-position:0 -160px,40px -110px}}}}
.streak{{position:absolute;left:-200px;right:-200px;height:440px;border-radius:50%;border-top:3px solid var(--a1);
  filter:drop-shadow(0 0 18px var(--a1)) drop-shadow(0 0 40px var(--a2));opacity:0;animation:fadein 1.4s ease-out both}}
.brand{{position:absolute;left:64px;top:64px;display:flex;align-items:center;gap:16px;font:800 34px Barlow;letter-spacing:3px;z-index:9;
  animation:fadein .8s ease-out both}}
.brand i{{width:46px;height:46px;border-radius:12px;background:linear-gradient(135deg,var(--a1),var(--a2));display:grid;place-items:center;
  font:900 22px Barlow;font-style:normal;color:#06060c}}
.brand span{{color:var(--a1)}}
.tag{{position:absolute;right:64px;top:74px;font:700 20px Mono;letter-spacing:4px;color:#9a9ab0;z-index:9;animation:fadein .8s .3s ease-out both}}
.h1{{font:900 132px/0.95 Barlow;letter-spacing:-1px;text-transform:none}}
.h2{{font:900 132px/0.95 Barlow;letter-spacing:-1px;background:linear-gradient(90deg,var(--a1),var(--a2),var(--a1));background-size:200% 100%;
  -webkit-background-clip:text;background-clip:text;color:transparent;animation:rise .9s .45s cubic-bezier(.2,.9,.2,1) both,sheen 4s 1.2s linear infinite}}
.sub{{font:500 38px/1.35 Inter;color:#c7c7d6}}
.rise{{animation:rise .9s cubic-bezier(.2,.9,.2,1) both}}
@keyframes rise{{from{{opacity:0;translate:0 70px}}to{{opacity:1;translate:0 0}}}}
@keyframes fadein{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes sheen{{to{{background-position:-200% 0}}}}
@keyframes pop{{0%{{opacity:0;scale:.85}}70%{{opacity:1;scale:1.03}}100%{{opacity:1;scale:1}}}}
@keyframes float{{0%,100%{{translate:0 0}}50%{{translate:0 -14px}}}}
.glass{{background:linear-gradient(180deg,rgba(28,28,42,.94),rgba(14,14,22,.94));border:1px solid rgba(255,255,255,.12);
  box-shadow:0 30px 80px -20px rgba(0,0,0,.8),0 0 0 1px color-mix(in srgb,var(--a1) 25%,transparent),0 0 80px -10px color-mix(in srgb,var(--a1) 45%,transparent)}}
.btn{{display:inline-flex;align-items:center;gap:14px;padding:26px 54px;border-radius:22px;font:700 38px Inter;color:white;
  background:linear-gradient(135deg,var(--a1),var(--a2));box-shadow:0 0 0 2px rgba(255,255,255,.25) inset,0 0 60px -6px var(--a1)}}
.feat{{display:flex;gap:18px;align-items:flex-start}}
.feat svg{{flex:0 0 54px;width:54px;height:54px;stroke:var(--a1);fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;
  filter:drop-shadow(0 0 10px var(--a1))}}
.feat b{{display:block;font:700 30px Inter;color:#f4f4fa}}.feat small{{font:500 24px Inter;color:#9a9ab0}}
.shot{{width:100%;height:100%;object-fit:cover;object-position:top}}
.end{{position:absolute;inset:0;z-index:20;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:44px;
  background:radial-gradient(800px 800px at 50% 45%,color-mix(in srgb,var(--a1) 30%,#06060c),#06060c 75%);opacity:0;animation:fadein .6s {dur-3.6:.2f}s ease-out both}}
.end .logo{{font:900 84px Barlow;letter-spacing:4px}}.end .logo span{{color:var(--a1)}}
.end .app{{font:900 150px/0.9 Barlow;background:linear-gradient(90deg,var(--a1),var(--a2));-webkit-background-clip:text;background-clip:text;color:transparent}}
.end .qr{{width:430px;height:430px;padding:26px;background:#fff;border-radius:34px;box-shadow:0 0 0 6px color-mix(in srgb,var(--a1) 70%,white),0 0 120px var(--a1)}}
.end .qr img{{width:100%;height:100%}}
.end .scan{{font:700 30px Mono;letter-spacing:6px;color:#c7c7d6}}
"""


def features_html(app, cls="", delay=0.0, step=0.35):
    out = []
    for i, (t, s) in enumerate(app["features"][:3]):
        out.append(f'<div class="feat {cls}" style="animation:rise .8s {delay + i * step:.2f}s cubic-bezier(.2,.9,.2,1) both">'
                   f'<svg viewBox="0 0 24 24">{ICONS[i % 3]}</svg><div><b>{esc(t)}</b><small>{esc(s)}</small></div></div>')
    return "".join(out)


def body(layout, app, shots, dur):
    host = app["url"].replace("https://", "").rstrip("/")
    desk, mob = shots["desk"], shots["mob"]
    h = f'<div class="h1 rise">{esc(app["h1"])}</div><div class="h2">{esc(app["h2"])}</div>'
    if layout == "browser":
        cards = "".join(
            f'<div class="glass" style="position:absolute;bottom:0;left:{x}px;width:300px;height:380px;border-radius:26px;padding:30px;'
            f'transform:rotate({r}deg);animation:rise .9s {4.2 + k * .25:.2f}s cubic-bezier(.2,.9,.2,1) both;overflow:hidden">'
            f'<div style="font:700 20px Mono;letter-spacing:3px;color:var(--a1)">0{k + 1}</div>'
            f'<div style="font:900 52px/1 Barlow;margin-top:18px">{esc(f[0])}</div><div style="font:500 24px Inter;color:#9a9ab0;margin-top:14px">{esc(f[1])}</div></div>'
            for k, (f, x, r) in enumerate(zip(app["features"][:3], (40, 380, 720), (-6, 0, 6))))
        return f"""
<div class="streak" style="top:860px;transform:rotate(-8deg)"></div>
<div style="position:absolute;left:64px;right:64px;top:190px;text-align:center">{h}</div>
<div class="glass" style="position:absolute;left:70px;right:70px;top:520px;height:700px;border-radius:30px;overflow:hidden;animation:pop 1s 1.6s both">
  <div style="height:70px;display:flex;align-items:center;gap:14px;padding:0 28px;background:rgba(10,10,18,.85);border-bottom:1px solid rgba(255,255,255,.08)">
    <i style="width:18px;height:18px;border-radius:50%;background:#ff5f57"></i><i style="width:18px;height:18px;border-radius:50%;background:#febc2e"></i><i style="width:18px;height:18px;border-radius:50%;background:#28c840"></i>
    <div style="margin-left:18px;flex:1;height:42px;border-radius:21px;background:rgba(255,255,255,.07);display:flex;align-items:center;padding:0 22px;font:500 24px Inter;color:#c7c7d6">&#128274;&nbsp; {esc(host)}</div></div>
  <img class="shot" src="{desk}" style="height:630px">
</div>
<div style="position:absolute;left:0;right:0;top:1150px;text-align:center;animation:pop .8s 3.2s both"><span class="btn">&#10022; {esc(app["cta"])}</span></div>
<div style="position:absolute;left:0;right:0;top:1300px;height:420px">{cards}</div>
<div style="position:absolute;left:64px;right:64px;bottom:70px;text-align:center;font:500 30px Inter;color:#9a9ab0;animation:fadein 1s 6s both">{esc(app["sub"])}</div>
"""
    if layout == "phone":
        phone = lambda x, y, r, d, z: (f'<div style="position:absolute;left:{x}px;top:{y}px;width:400px;height:840px;border-radius:64px;padding:16px;'
                                      f'background:#111118;border:2px solid rgba(255,255,255,.18);transform:rotate({r}deg);z-index:{z};'
                                      f'box-shadow:0 40px 100px -20px #000,0 0 90px -10px var(--a1);animation:rise 1s {d}s cubic-bezier(.2,.9,.2,1) both">'
                                      f'<div style="width:100%;height:100%;border-radius:50px;overflow:hidden;background:#000"><img class="shot" src="{mob}"></div></div>')
        return f"""
<div class="streak" style="top:1060px;transform:rotate(10deg)"></div>
<div style="position:absolute;left:64px;right:64px;top:180px">{h}<p class="sub rise" style="margin-top:30px;max-width:900px;animation-delay:1s">{esc(app["sub"])}</p></div>
{phone(110, 720, -8, 1.6, 2)}{phone(560, 680, 7, 2.0, 3)}
<div class="glass" style="position:absolute;left:470px;top:1180px;z-index:5;border-radius:26px;padding:26px 34px;animation:pop .8s 3.4s both">
  <div style="font:900 96px/1 Barlow;color:var(--a1)">{esc(app["stat"])}</div><div style="font:600 26px Inter;color:#c7c7d6">{esc(app["statLabel"])}</div></div>
<div class="glass" style="position:absolute;left:64px;right:64px;bottom:90px;border-radius:30px;padding:40px;display:grid;gap:30px;z-index:6;animation:rise .9s 4.6s both">
  {features_html(app, delay=5.0)}</div>
"""
    if layout == "split":
        nums = "".join(
            f'<div style="display:flex;gap:30px;align-items:baseline;padding:28px 0;border-top:1px solid rgba(255,255,255,.1);animation:rise .8s {4.0 + k * .45:.2f}s both">'
            f'<div style="font:900 90px/1 Barlow;color:var(--a1);width:130px">0{k + 1}</div><div><div style="font:800 52px/1 Barlow">{esc(f[0])}</div>'
            f'<div style="font:500 28px Inter;color:#9a9ab0;margin-top:8px">{esc(f[1])}</div></div></div>' for k, f in enumerate(app["features"][:3]))
        return f"""
<div style="position:absolute;left:-80px;right:-80px;top:150px;height:760px;perspective:1600px">
  <div class="glass" style="width:100%;height:100%;border-radius:36px;overflow:hidden;transform:rotateX(14deg) rotateZ(-4deg);animation:pop 1.1s .2s both">
    <img class="shot" src="{desk}"></div></div>
<div style="position:absolute;left:0;right:0;top:600px;height:420px;background:linear-gradient(transparent,#06060c 80%)"></div>
<div style="position:absolute;left:64px;right:64px;top:880px">{h}</div>
<div style="position:absolute;left:64px;right:64px;top:1250px">{nums}</div>
"""
    if layout == "stat":
        rings = "".join(f'<div style="position:absolute;left:50%;top:50%;width:{s}px;height:{s}px;margin:-{s // 2}px 0 0 -{s // 2}px;border-radius:50%;'
                        f'border:2px solid color-mix(in srgb,var(--a1) {a}%,transparent);animation:pop 1.2s {d}s both"></div>'
                        for s, a, d in ((520, 70, .3), (760, 40, .5), (1000, 22, .7)))
        pills = "".join(f'<span class="glass" style="padding:18px 30px;border-radius:999px;font:600 28px Inter;animation:pop .7s {5.2 + k * .3:.2f}s both">{esc(f[0])}</span>'
                        for k, f in enumerate(app["features"][:3]))
        return f"""
<div style="position:absolute;left:0;right:0;top:170px;height:900px">{rings}
  <div style="position:absolute;left:0;right:0;top:260px;text-align:center;font:900 300px/1 Barlow;background:linear-gradient(180deg,#fff,var(--a1));
   -webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 40px var(--a1));animation:pop 1s .4s both">{esc(app["stat"])}</div>
  <div style="position:absolute;left:0;right:0;top:600px;text-align:center;font:700 30px Mono;letter-spacing:6px;color:#c7c7d6;animation:fadein 1s 1s both">{esc(app["statLabel"]).upper()}</div></div>
<div style="position:absolute;left:64px;right:64px;top:930px;text-align:center">{h}</div>
<div class="glass" style="position:absolute;left:200px;right:200px;top:1250px;height:380px;border-radius:30px;overflow:hidden;animation:rise 1s 3.6s both,float 5s 4.6s ease-in-out infinite">
  <img class="shot" src="{desk}"></div>
<div style="position:absolute;left:40px;right:40px;bottom:90px;display:flex;gap:16px;justify-content:center;flex-wrap:wrap">{pills}</div>
"""
    # stack
    stack = "".join(f'<div class="glass" style="position:absolute;left:{120 + k * 40}px;right:{120 - k * 40}px;top:{240 + k * 150}px;height:640px;border-radius:30px;overflow:hidden;'
                    f'transform:rotate({(k - 1) * 4}deg);animation:rise 1s {.3 + k * .45:.2f}s cubic-bezier(.2,.9,.2,1) both">'
                    f'<img class="shot" src="{desk if k != 1 else mob}" style="object-position:{["top", "center", "bottom"][k]}"></div>' for k in range(3))
    return f"""
<div class="streak" style="top:620px;transform:rotate(-12deg)"></div>
{stack}
<div style="position:absolute;left:0;right:0;top:1000px;height:300px;background:linear-gradient(transparent,#06060c)"></div>
<div style="position:absolute;left:64px;right:64px;top:1180px">{h}<p class="sub rise" style="margin-top:26px;animation-delay:1.4s">{esc(app["sub"])}</p></div>
<div class="glass" style="position:absolute;left:64px;right:64px;bottom:80px;border-radius:28px;padding:28px 36px;display:flex;align-items:center;justify-content:space-between;animation:rise .9s 4.2s both">
  <div style="font:900 64px/1 Barlow;color:var(--a1)">{esc(app["stat"])} <span style="font:600 26px Inter;color:#c7c7d6">{esc(app["statLabel"])}</span></div>
  <span class="btn" style="padding:20px 34px;font-size:30px">{esc(app["cta"])}</span></div>
"""


def page(layout, app, shots, qr, dur):
    a1, a2 = app.get("accent", ["#22d3ee", "#a855f7"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{head_css(a1, a2, dur)}</style></head><body>
<div class="stage"><div class="bg"></div><div class="dots"></div>
<div class="brand"><i>H</i>HSW365 <span>{esc(app["name"]).upper()}</span></div><div class="tag">HSW365.CO</div>
{body(layout, app, shots, dur)}</div>
<div class="end"><div class="logo">HSW365 <span>MEDIA</span></div><div class="app">{esc(app["name"])}</div>
<div class="qr"><img src="{qr}"></div><div class="btn">{esc(app["cta"])}</div><div class="scan">SCAN TO SIGN UP</div></div>
<script>/* every headline line stays on ONE line: shrink it until it fits its column */
document.fonts.ready.then(() => document.querySelectorAll(".h1,.h2").forEach(el => {{
  el.style.whiteSpace = "nowrap"; el.style.display = "inline-block";
  const max = el.parentElement.clientWidth; let fs = parseFloat(getComputedStyle(el).fontSize);
  while (el.scrollWidth > max && fs > 60) {{ fs -= 4; el.style.fontSize = fs + "px"; }}
  el.style.display = "block"; document.body.dataset.fit = "1";
}}));</script>
</body></html>"""


async def render_frames(html_path, frames_dir, dur):
    from playwright.async_api import async_playwright
    n = int(dur * FPS)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": W, "height": H})
        await pg.goto("file://" + html_path)
        await pg.wait_for_function("document.body.dataset.fit === '1'", timeout=15000)
        await pg.wait_for_timeout(600)
        await pg.evaluate("document.getAnimations().forEach(a => a.pause())")
        for i in range(n):
            t = i / FPS * 1000
            await pg.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {t})")
            await pg.screenshot(path=os.path.join(frames_dir, f"f{i:05d}.jpg"), type="jpeg", quality=90)
        await b.close()
    return n


# ------------------------------------------------------------------ sound
async def _tts(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-4%", pitch="-6Hz").save(out)


def narrate(lines, workdir):
    """One narrator track; returns (path, seconds) or (None, 0) if no voice service is reachable."""
    parts = []
    for i, line in enumerate(lines):
        mp3 = os.path.join(workdir, f"vo{i}.mp3")
        try:
            asyncio.run(_tts(line, mp3))
            parts.append(mp3)
        except Exception as e:
            print(f"[showcase] narrator line {i + 1} failed: {e}")
    if not parts:
        return None, 0.0
    lst = os.path.join(workdir, "vo.txt")
    gap = os.path.join(workdir, "gap.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.45", gap], check=True)
    with open(lst, "w") as f:
        for p in parts:
            wav = p.replace(".mp3", ".wav")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", p, "-ar", "44100", "-ac", "1", wav], check=True)
            f.write(f"file '{wav}'\nfile '{gap}'\n")
    out = os.path.join(workdir, "vo.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-af", "loudnorm=I=-15:TP=-1.5,equalizer=f=150:t=q:w=1:g=2.5", out], check=True)
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                                capture_output=True, text=True).stdout.strip() or 0)
    return out, secs


def score(path, dur, end_at):
    """Trailer-style bed: low pulse, riser into each section, hits on the headline, the screen and the end card."""
    SR = 44100
    n = int(SR * dur)
    a = np.zeros(n)
    rng = np.random.default_rng(7)

    def seg(t0, d):
        i0 = int(t0 * SR)
        m = max(0, min(n - i0, int(d * SR)))
        return i0, m, np.arange(m) / SR

    def hit(t0, amp=1.0):
        i0, m, x = seg(t0, 2.0)
        f = 40 + 120 * np.exp(-x * 10)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 2.2)
        nz = np.convolve(rng.normal(0, 1, m), np.ones(20) / 20, "same") * np.exp(-x * 16)
        a[i0:i0 + m] += amp * (0.9 * s + 0.5 * nz)

    def riser(t0, t1, amp=0.2):
        i0, m, x = seg(t0, t1 - t0)
        p = x / max(1e-6, t1 - t0)
        nz = rng.normal(0, 1, m)
        a[i0:i0 + m] += amp * (nz - np.convolve(nz, np.ones(4) / 4, "same")) * p ** 2.4 * 0.6

    def pulse(t0, t1):
        for k, tb in enumerate(np.arange(t0, t1, 0.5)):
            i0, m, x = seg(tb, 0.35)
            a[i0:i0 + m] += (0.38 if k % 2 == 0 else 0.2) * np.sin(2 * np.pi * np.cumsum(48 + 55 * np.exp(-x * 30)) / SR) * np.exp(-x * 10)

    def pad(t0, t1, freqs, amp):
        i0, m, x = seg(t0, t1 - t0)
        s = sum(np.sin(2 * np.pi * f * x + .4 * np.sin(2 * np.pi * .15 * x + j)) for j, f in enumerate(freqs)) / len(freqs)
        a[i0:i0 + m] += amp * s * np.clip(x / .8, 0, 1) * np.clip(((t1 - t0) - x) / .6, 0, 1)

    pad(0, dur, (55, 82.4, 110, 164.8), 0.11)
    riser(0, 0.5, .15); hit(0.45, .9)
    riser(1.0, 1.6, .2); hit(1.6, .7)
    pulse(2.0, end_at - 0.2)
    riser(end_at - 1.2, end_at, .28); hit(end_at, 1.0)
    a = np.tanh(a * 1.1) * 0.6
    pcm = (a * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ build
def pick_layout(app_id, app, forced=None):
    if forced:
        return forced
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {"recent": []}
    want = app.get("layout")
    recent = st.get("recent", [])[-2:]
    if want and want not in recent[-1:]:
        layout = want
    else:  # never the same composition twice in a row
        layout = next((l for l in LAYOUTS if l not in recent), LAYOUTS[0])
    st["recent"] = (st.get("recent", []) + [layout])[-6:]
    st.setdefault("by_app", {})[app_id] = layout
    json.dump(st, open(STATE, "w"), indent=2)
    return layout


def build(app_id, out_path, layout=None):
    cfg = json.load(open(CFG))
    app = cfg["apps"][app_id]
    layout = pick_layout(app_id, app, layout)
    work = tempfile.mkdtemp(prefix=f"showcase-{app_id}-")
    print(f"[showcase] {app['name']}: layout={layout}")
    raw = asyncio.run(capture(app["url"], work))
    shots = {k: data_uri(v) for k, v in raw.items()}
    vo, vo_len = narrate(app.get("vo", []), work)
    dur = round(max(15.0, vo_len + 4.2), 2)
    html_path = os.path.join(work, "ad.html")
    with open(html_path, "w") as f:
        f.write(page(layout, app, shots, qr_svg(app.get("signup") or app["url"]), dur))
    frames = os.path.join(work, "frames")
    os.makedirs(frames)
    asyncio.run(render_frames(html_path, frames, dur))
    bed = os.path.join(work, "score.wav")
    score(bed, dur, dur - 3.6)
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "f%05d.jpg"), "-i", bed]
    if vo:
        cmd += ["-i", vo, "-filter_complex",
                "[2:a]adelay=500|500,apad[v];[1:a][v]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=300[b];"
                "[b][v]amix=inputs=2:duration=first:weights='0.8 1.4'[a]", "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True)
    cover = out_path.rsplit(".", 1)[0] + ".jpg"
    subprocess.run(["cp", os.path.join(frames, f"f{int((dur - 5) * FPS):05d}.jpg"), cover])
    print(f"[showcase] wrote {out_path} ({dur}s, narrator={'yes' if vo else 'no'})")
    return out_path, layout


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("out")
    ap.add_argument("--layout", choices=LAYOUTS)
    a = ap.parse_args()
    build(a.app, a.out, a.layout)
