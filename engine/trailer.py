"""iRun trailer ads: every ad is a ~19s vertical micro-drama cut like a movie trailer.

Structure (fixed, timings derived from the spec):
  open      cold-open spectacle shot, optional rubber-stamp impact word + ink burst (no logo, no talking)
  title     title slam over red smoke
  scenes    2-5 close-up reaction cuts (~1.1s each) with one-line subtitles; a scene may be a "card"
            (rendered UI panel with flagged rows) instead of a photo
  slams     exactly 3 giant outlined neon words, one per beat, each over its own shot (+ optional progress panel)
  callback  the opening shot again, with the payoff impact word
  payoff    1-2 warm resolution shots
  flash     accent-colour flash
  end       wordmark, tagline, QR straight to the product's sign-up, CTA, fine print
Score is synthesized (booms, braams, risers, ticking pulse). No voiceover.

Shots are full-res 1080x1920 stills made with Canva (see engine/canva_shots.py) in spec["shots_dir"].

Spec (queue item with "kind": "trailer"):
{
  "kind": "trailer", "account": "hoodstar365", "product": "dispute365", "platform": "instagram",
  "shots_dir": "content/shots/<slug>", "accent": "#ef4444", "title": "DISPUTE365",
  "open": {"shot": "stamp", "impact": "DENIED", "cy": 0.42},
  "scenes": [{"shot": "officer", "sub": "..."}, {"card": {"title": "...", "rows": [["A", "detail"], ...], "tag": "ERROR"}}, ...],
  "slams": [{"word": "FIGHT", "shot": "night"}, {"word": "IT", "shot": "night", "panel": {...}}, {"word": "BACK", "shot": "envelope"}],
  "callback": {"shot": "stamp", "impact": "DELETED"},
  "payoff": [{"shot": "keys"}, {"shot": "hero", "sub": "Turn negative into positive."}],
  "end": {"wordmark": ["DISPUTE", "365"], "tagline": "...", "cta": "SCAN TO SIGN UP", "lines": ["...", "..."],
          "fine": "...", "link": "https://...#signup"},
  "caption": "...", "hashtags": ["..."]
}
Shot options: "cy"/"cx" focus point (0-1), "zoom" [from, to], "warm" true for golden scenes, "sat" saturation.
Panel: {"label": "APP", "title": "3 ERRORS FOUND", "working": "WRITING...", "done": "3 LETTERS READY", "steps": ["LETTER 1", ...]}

  python engine/trailer.py content/queue/x.json out.mp4             full render
  python engine/trailer.py content/queue/x.json out preview 1.2,8   stills
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FONTS = os.path.join(ROOT, "assets", "fonts")
INTER = "/usr/share/fonts/opentype/inter/"
W, H, FPS = 1080, 1920, 30
XB, SB, MONO = "BarlowCondensed-ExtraBold.ttf", "BarlowCondensed-SemiBold.ttf", "SpaceMono-Bold.ttf"
BASE = (10, 10, 15); WHITE = (245, 246, 250); MUTED = (141, 140, 156)


def FB(n, s): return ImageFont.truetype(os.path.join(FONTS, n), s)


def FI(n, s):
    try:
        return ImageFont.truetype(INTER + n, s)
    except OSError:
        return FB(SB, s)


def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_io(x): x = clamp(x); return 3 * x * x - 2 * x * x * x
def hexrgb(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clean(item):
    """Validate a trailer item. Returns the script dict iRun logs (beats = subtitles + slam words)."""
    for k in ("shots_dir", "title", "open", "scenes", "slams", "callback", "payoff", "end"):
        if k not in item:
            raise ValueError(f"trailer needs '{k}'")
    if len(item["slams"]) != 3:
        raise ValueError("trailer needs exactly 3 slam words")
    if not 2 <= len(item["scenes"]) <= 5 or not 1 <= len(item["payoff"]) <= 2:
        raise ValueError("trailer needs 2-5 scenes and 1-2 payoff shots")
    if not item["end"].get("link"):
        raise ValueError("trailer end card needs the sign-up link for the QR")
    d = os.path.join(ROOT, item["shots_dir"])
    names = [item["open"]["shot"], item["callback"]["shot"]] + [s["shot"] for s in item["scenes"] if "shot" in s] \
        + [s["shot"] for s in item["slams"]] + [s["shot"] for s in item["payoff"]]
    for n in set(names):
        if not any(os.path.exists(os.path.join(d, n + e)) for e in (".jpg", ".png")):
            raise ValueError(f"missing shot {n} in {item['shots_dir']}")
    subs = [s.get("sub", "") for s in item["scenes"] + item["payoff"] if s.get("sub")]
    words = [s["word"] for s in item["slams"]]
    beats = (subs[:2] + words + subs[2:])[:9] or words
    while len(beats) < 3:
        beats.append(item["title"])
    tags = [str(t).lstrip("#").replace(" ", "") for t in item.get("hashtags", [])][:6]
    return {"beats": beats, "emphasis": [""] * len(beats), "caption": str(item.get("caption", "")).strip(), "hashtags": tags}


class Trailer:
    def __init__(self, spec):
        self.s = spec
        self.acc = hexrgb(spec.get("accent", "#ef4444"))
        d = os.path.join(ROOT, spec["shots_dir"])
        self.img = {}
        for f in os.listdir(d):
            n, e = os.path.splitext(f)
            if e.lower() in (".jpg", ".jpeg", ".png"):
                a = cv2.cvtColor(cv2.imread(os.path.join(d, f)), cv2.COLOR_BGR2RGB)
                if a.shape[:2] != (H, W):
                    a = self._cover(a)
                self.img[n] = a.astype(np.float32)
        self._timeline()
        self._static()

    @staticmethod
    def _cover(a):
        h, w = a.shape[:2]; s = max(W / w, H / h)
        a = cv2.resize(a, (int(w * s + 1), int(h * s + 1)), interpolation=cv2.INTER_LANCZOS4)
        y0 = (a.shape[0] - H) // 2; x0 = (a.shape[1] - W) // 2
        return a[y0:y0 + H, x0:x0 + W]

    # ---------- timeline ----------
    def _timeline(self):
        s = self.s; segs = []; t = 0.0
        def add(kind, dur, **kw):
            nonlocal t
            segs.append(dict(kind=kind, t0=t, t1=t + dur, **kw)); t += dur
        add("open", 1.8, **s["open"])
        add("title", 1.2)
        for i, sc in enumerate(s["scenes"]):
            add("card" if "card" in sc else "scene", 1.4 if "card" in sc else 1.0 if i == len(s["scenes"]) - 1 else 1.1, **sc)
        for sl in s["slams"]:
            add("slam", 1.1, **sl)
        add("callback", 1.2, **s["callback"])
        for i, p in enumerate(s["payoff"]):
            add("payoff", 1.8 if i == len(s["payoff"]) - 1 else 1.1, **p)
        add("flash", 0.25)
        add("end", 3.75)
        self.segs = segs; self.dur = t; self.n = int(round(t * FPS))
        self.cuts = [g["t0"] for g in segs[1:]]

    # ---------- static layers ----------
    def _static(self):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.yy, self.xx = yy, xx
        self.vig = np.clip(1.25 - 0.85 * (((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.58)) ** 2), 0.18, 1)[..., None]
        r = np.random.default_rng(7)
        self.grain = [r.normal(0, 7.5, (H // 2, W // 2, 1)).astype(np.float32).repeat(2, 0).repeat(2, 1) for _ in range(8)]
        hot = tuple(min(255, int(c * 0.6 + 255 * 0.4)) for c in self.acc)
        f_slam = FB(XB, 470)
        self.slam = {}
        for sl in self.s["slams"]:
            w = sl["word"].upper()
            self.slam[w] = (self.text(w, f_slam, stroke=7, stroke_fill=hot + (255,), glow=22, spacing=18),
                            self.text(w, f_slam, stroke=3, stroke_fill=(255, 238, 238, 255), spacing=18))
        f_title = FB(XB, 205)
        title = self.s["title"].upper()
        while f_title.size > 90 and f_title.getlength(title) > W * 0.86:
            f_title = FB(XB, f_title.size - 10)
        self.title = self.text(title, f_title, fill=WHITE + (255,), glow=26, spacing=4)
        self.presents = self.text(self.s.get("presents", "HSW365 MEDIA PRESENTS"), FB(MONO, 30), fill=(200, 200, 210, 255), spacing=8)
        self.impact = {g["impact"]: self.stamp_word(g["impact"]) for g in self.segs if g.get("impact")}
        self.f_sub = FI("Inter-SemiBold.otf", 52)
        self.end = self.end_layer()
        r = np.random.default_rng(3); n = 70
        self.emb = dict(x=r.uniform(0, W, n), y0=r.uniform(0, H, n), v=r.uniform(40, 160, n), s=r.uniform(1.2, 3.6, n), ph=r.uniform(0, 6.28, n))
        self.bursts = []
        for k, g in enumerate(self.segs):
            if g.get("impact"):
                rr = np.random.default_rng(k + 1); m = 170
                ang = rr.uniform(-np.pi, 0.15, m); sp = rr.uniform(0.25, 1, m) * 900
                self.bursts.append(dict(t0=g["t0"] + (1.05 if g["kind"] == "open" else 0.35), vx=np.cos(ang) * sp, vy=np.sin(ang) * sp,
                                        sz=rr.uniform(2, 7, m), life=rr.uniform(0.5, 1.4, m)))
                g["hit"] = self.bursts[-1]["t0"]

    def text(self, text, font, fill=None, stroke=0, stroke_fill=None, glow=0, spacing=0):
        pad = stroke + glow + 20
        tw = int(font.getlength(text) + spacing * max(0, len(text) - 1)) + 2 * pad
        asc, desc = font.getmetrics(); th = asc + desc + 2 * pad
        lay = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); x = pad
        for ch in text:
            d.text((x, pad), ch, font=font, fill=fill or (0, 0, 0, 0), stroke_width=stroke, stroke_fill=stroke_fill)
            x += font.getlength(ch) + spacing
        if glow:
            g = lay.getchannel("A").filter(ImageFilter.GaussianBlur(glow))
            gl = Image.new("RGBA", lay.size, self.acc + (0,)); gl.putalpha(g.point(lambda v: min(255, int(v * 1.6))))
            gl.alpha_composite(lay); lay = gl
        return lay

    def stamp_word(self, word):
        f = FB(XB, 200); word = word.upper(); tw = int(f.getlength(word)) + 120; th = 300
        lay = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.rounded_rectangle((10, 10, tw - 10, th - 10), radius=18, outline=self.acc + (255,), width=16)
        d.text((60, 18), word, font=f, fill=self.acc + (255,))
        a = np.asarray(lay).copy()
        noise = cv2.GaussianBlur(np.random.default_rng(len(word)).random((th, tw)).astype(np.float32), (0, 0), 1.6)
        a[..., 3] = (a[..., 3] * np.clip((noise - 0.30) * 3.2, 0.15, 1)).astype(np.uint8)
        return Image.fromarray(a)

    def card(self, c, nflag, scan):
        f_hdr = FB(MONO, 30); f_row = FB(SB, 54); f_rowS = FB(MONO, 26); f_tag = FB(XB, 40)
        rows = c.get("rows", [])[:4]; cw = 900; ch = 140 + 210 * len(rows) - 50
        lay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=36, fill=(19, 19, 28, 238), outline=(51, 51, 63, 255), width=2)
        d.text((48, 44), c.get("title", "").upper(), font=f_hdr, fill=MUTED + (255,))
        d.line((48, 100, cw - 48, 100), fill=(51, 51, 63, 255), width=2)
        tag = c.get("tag", "ERROR").upper(); tagw = f_tag.getlength(tag) + 36
        for i, (a_, b_) in enumerate(rows):
            y = 140 + i * 210
            d.text((48, y), a_.upper(), font=f_row, fill=WHITE + (255,))
            d.text((48, y + 72), b_.upper(), font=f_rowS, fill=MUTED + (255,))
            if i < nflag:
                d.rounded_rectangle((cw - 48 - tagw, y + 14, cw - 48, y + 82), radius=12, fill=self.acc + (255,))
                d.text((cw - 48 - tagw + 18, y + 18), tag, font=f_tag, fill=(255, 255, 255, 255))
            if i < len(rows) - 1:
                d.line((48, y + 160, cw - 48, y + 160), fill=(36, 36, 47, 255), width=2)
        if scan is not None:
            sy = int(110 + scan * (ch - 150))
            beam = Image.new("RGBA", (cw, 80), (0, 0, 0, 0)); bd = ImageDraw.Draw(beam)
            for k in range(80):
                bd.line((0, k, cw, k), fill=self.acc + (int(110 * (1 - abs(k - 40) / 40) ** 2),))
            lay.alpha_composite(beam, (0, max(0, min(ch - 80, sy - 40))))
        return lay

    def panel(self, pn, p):
        f_hdr = FB(MONO, 30); f_ui = FB(XB, 92); f_uiS = FB(MONO, 30)
        steps = pn.get("steps", [])[:3]; cw, ch = 900, 560 if steps else 400
        lay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=36, fill=(19, 19, 28, 240), outline=(51, 51, 63, 255), width=2)
        d.text((48, 44), pn.get("label", self.s["title"]).upper(), font=f_hdr, fill=self.acc + (255,))
        d.text((48, 110), pn.get("title", "").upper(), font=f_ui, fill=WHITE + (255,))
        d.rounded_rectangle((48, 250, cw - 48, 280), radius=15, fill=(36, 36, 47, 255))
        d.rounded_rectangle((48, 250, 48 + max(30, int((cw - 96) * ease(p))), 280), radius=15, fill=self.acc + (255,))
        msg = pn.get("working", "WORKING...") if p < 1 else pn.get("done", "DONE")
        d.text((48, 312), msg.upper(), font=f_uiS, fill=(MUTED if p < 1 else WHITE) + (255,))
        for k, st in enumerate(steps):
            on = p > (k + 1) / (len(steps) + 0.2); x = 48 + k * 276
            d.rounded_rectangle((x, 380, x + 252, 510), radius=18, fill=(30, 30, 42, 255), outline=(self.acc if on else (51, 51, 63)) + (255,), width=3)
            d.text((x + 24, 404), st.upper(), font=f_uiS, fill=(WHITE if on else MUTED) + (255,))
            d.text((x + 24, 452), "READY" if on else "...", font=f_uiS, fill=(self.acc if on else MUTED) + (255,))
        return lay

    def end_layer(self):
        import segno
        e = self.s["end"]; lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        wm = e.get("wordmark") or [self.s["title"].upper(), ""]
        f_end = FB(XB, 168)
        while f_end.size > 80 and f_end.getlength("".join(wm)) > W * 0.88:
            f_end = FB(XB, f_end.size - 8)
        w1 = f_end.getlength(wm[0]); w2 = f_end.getlength(wm[1]) if len(wm) > 1 else 0; x = (W - w1 - w2) / 2
        d.text((x, 250), wm[0], font=f_end, fill=WHITE + (255,))
        if len(wm) > 1:
            d.text((x + w1, 250), wm[1], font=f_end, fill=self.acc + (255,))
        f_tagl = FB(SB, 62)
        for k, line in enumerate(_wrap(e.get("tagline", ""), f_tagl, W * 0.88)[:2]):
            d.text(((W - f_tagl.getlength(line)) / 2, 460 + k * 70), line, font=f_tagl, fill=(220, 220, 228, 255))
        buf = io.BytesIO(); size, pad = 440, 30
        segno.make(e["link"], error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
        code = Image.open(buf).convert("RGBA").resize((size - 2 * pad, size - 2 * pad), Image.NEAREST)
        q = Image.new("RGBA", (size, size), (0, 0, 0, 0)); qd = ImageDraw.Draw(q)
        qd.rounded_rectangle((0, 0, size - 1, size - 1), radius=34, fill=(255, 255, 255, 255)); q.alpha_composite(code, (pad, pad))
        lay.alpha_composite(q, ((W - size) // 2, 640))
        f_cta = FB(XB, 64); f_small = FB(MONO, 28); f_tiny = FI("Inter-Medium.otf", 26)
        t = e.get("cta", "SCAN TO SIGN UP").upper(); d.text(((W - f_cta.getlength(t)) / 2, 1112), t, font=f_cta, fill=self.acc + (255,))
        for k, t in enumerate(e.get("lines", [])[:3]):
            fs = f_small
            while fs.size > 18 and fs.getlength(t) > W * 0.92:
                fs = FB(MONO, fs.size - 2)
            d.text(((W - fs.getlength(t)) / 2, 1220 + k * 52), t, font=fs, fill=(WHITE if k == 0 else MUTED) + (255,))
        for k, line in enumerate(_wrap(e.get("fine", ""), f_tiny, W * 0.86)[:2]):
            d.text(((W - f_tiny.getlength(line)) / 2, 1690 + k * 34), line, font=f_tiny, fill=(110, 110, 124, 255))
        t = "HSW365 MEDIA"; d.text(((W - f_small.getlength(t)) / 2, 1770), t, font=f_small, fill=(150, 150, 162, 255))
        return lay

    # ---------- drawing ----------
    def grade(self, a, warm=0.0, sat=1.0, contrast=1.12):
        lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
        a = lum[..., None] + (a - lum[..., None]) * sat
        a = (a - 128) * contrast + 128
        sh = np.clip(1 - lum / 140, 0, 1)[..., None]
        a = a + sh * np.array([-10, 4, 12], np.float32) * (1 - warm)
        hi = np.clip((lum - 120) / 135, 0, 1)[..., None]
        return a + hi * np.array([14, 6, -10], np.float32) * (0.5 + warm)

    def shot(self, name, p, z0, z1, cx=0.5, cy=0.42, shake=(0, 0), warm=False, sat=1.0, contrast=1.12):
        z = z0 + (z1 - z0) * ease_io(p); ox, oy = cx * W, cy * H
        M = np.float32([[z, 0, W / 2 - z * ox + shake[0]], [0, z, H / 2 - z * oy + shake[1]]])
        a = cv2.warpAffine(self.img[name], M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        return self.grade(a, warm=0.85 if warm else 0.0, sat=sat, contrast=contrast)

    def comp(self, arr, lay, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
        if alpha <= 0.01:
            return arr
        if scale != 1.0:
            lay = lay.resize((max(1, int(lay.width * scale)), max(1, int(lay.height * scale))), Image.LANCZOS)
        if rot:
            lay = lay.rotate(rot, resample=Image.BICUBIC, expand=True)
        l = np.asarray(lay).astype(np.float32)
        x0 = int(cx - l.shape[1] / 2); y0 = int(cy - l.shape[0] / 2)
        sx0, sy0 = max(0, -x0), max(0, -y0); x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(W, x0 + l.shape[1]), min(H, y0 + l.shape[0])
        if x1c <= x0c or y1c <= y0c:
            return arr
        sub = l[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)]; a = sub[..., 3:4] / 255 * alpha
        arr[y0c:y1c, x0c:x1c] = arr[y0c:y1c, x0c:x1c] * (1 - a) + sub[..., :3] * a
        return arr

    def subtitle(self, arr, text, a):
        lay = self.text(text, self.f_sub, fill=(250, 250, 252, 255))
        sh = self.text(text, self.f_sub, fill=(0, 0, 0, 200)).filter(ImageFilter.GaussianBlur(6))
        self.comp(arr, sh, W / 2, 1503, alpha=a); return self.comp(arr, lay, W / 2, 1500, alpha=a)

    def embers(self, arr, t, amt):
        e = self.emb; ov = np.zeros((H, W), np.float32)
        ys = (e["y0"] - e["v"] * t) % H; xs = e["x"] + 30 * np.sin(t * 1.3 + e["ph"]); fl = 0.5 + 0.5 * np.sin(t * 7 + e["ph"] * 3)
        for X, Y, s, f in zip(xs, ys, e["s"], fl):
            cv2.circle(ov, (int(X), int(Y)), int(s + 0.5), float(0.5 + 0.5 * f), -1, cv2.LINE_AA)
        hot = np.array([min(255, c + 40) for c in self.acc], np.float32)
        arr += (cv2.GaussianBlur(ov, (0, 0), 3) * 1.8 + ov)[..., None] * hot * 0.6 * amt

    def burst(self, arr, t):
        for b in self.bursts:
            dt = t - b["t0"]
            if dt < 0 or dt > 1.5:
                continue
            px = 560 + b["vx"] * dt; py = 860 + b["vy"] * dt + 700 * dt * dt; al = np.clip(1 - dt / b["life"], 0, 1)
            ov = np.zeros((H, W), np.float32)
            for X, Y, s, a in zip(px, py, b["sz"], al):
                if a > 0 and 0 <= X < W and 0 <= Y < H:
                    cv2.circle(ov, (int(X), int(Y)), int(s), float(a), -1, cv2.LINE_AA)
            arr += (cv2.GaussianBlur(ov, (0, 0), 6) * 1.5 + ov)[..., None] * np.array(self.acc, np.float32) * 0.9

    @staticmethod
    def shake(t, t0, amp=26):
        dt = t - t0
        if dt < 0 or dt > 0.4:
            return (0, 0)
        k = amp * np.exp(-dt * 11); return (k * np.sin(dt * 95), k * np.cos(dt * 77))

    def fade(self, t, g, a=0.15):
        return clamp((t - g["t0"] - a) * 5) * clamp((g["t1"] - 0.05 - t) * 8)

    def frame(self, i):
        t = i / FPS
        g = next((x for x in self.segs if x["t0"] <= t < x["t1"]), self.segs[-1])
        p = (t - g["t0"]) / (g["t1"] - g["t0"]); k = g["kind"]
        zoom = g.get("zoom")
        if k in ("open", "callback"):
            hit = g.get("hit", g["t0"] + 0.35); sh = self.shake(t, hit)
            z = zoom or ([1.32, 1.16] if k == "open" else [1.2, 1.1])
            arr = self.shot(g["shot"], p, z[0], z[1], g.get("cx", 0.5), g.get("cy", 0.42), sh, contrast=1.2)
            if g.get("impact") and t >= hit:
                q = (t - hit) / 0.1
                self.comp(arr, self.impact[g["impact"]], W / 2 + sh[0], 1280 + sh[1], 1.5 - 0.5 * ease(q), clamp(q * 2), rot=7 if k == "open" else -6)
            self.burst(arr, t)
            if hit <= t < hit + 0.07:
                arr = arr * 0.4 + 255 * 0.6
        elif k == "title":
            src = self.segs[0]["shot"]
            bg = cv2.GaussianBlur(self.shot(src, 0.5, 1.6, 1.6, cy=0.3, sat=0.0, contrast=0.9), (0, 0), 28) * 0.35
            arr = bg * (0.35 + 0.95 * np.array(self.acc, np.float32) / 255)
            self.embers(arr, t, 0.8)
            self.comp(arr, self.title, W / 2, H / 2, 1.14 - 0.14 * ease(p * 3), clamp(p * 6))
            self.comp(arr, self.presents, W / 2, H / 2 - 190, 1.0, clamp((p - 0.15) * 4))
            if t < g["t0"] + 0.06:
                arr = arr * 0.3 + 255 * 0.7
        elif k == "scene":
            z = zoom or [1.08, 1.18]
            arr = self.shot(g["shot"], p, z[0], z[1], g.get("cx", 0.5), g.get("cy", 0.4), warm=g.get("warm", False), sat=g.get("sat", 1.0))
            if g.get("tense"):
                arr = arr * (0.55 + 0.45 * self.vig) + (1 - self.vig) * np.array(self.acc, np.float32) * 0.25
            if g.get("sub"):
                self.subtitle(arr, g["sub"], self.fade(t, g))
        elif k == "card":
            bgname = g.get("bg") or next(iter(self.img))
            arr = cv2.GaussianBlur(self.shot(bgname, 0.3, 1.3, 1.3, sat=0.4), (0, 0), 20) * 0.35
            rows = len(g["card"].get("rows", [])); dur = g["t1"] - g["t0"]
            nflag = min(rows, int(max(0, t - g["t0"] - 0.35) / ((dur - 0.6) / max(1, rows))) + (1 if t - g["t0"] > 0.35 else 0))
            scan = clamp((t - g["t0"] - 0.05) / (dur - 0.25)) if t < g["t1"] - 0.15 else None
            self.comp(arr, self.card(g["card"], nflag, scan), W / 2, H / 2, 1.04 - 0.04 * ease(p), clamp(p * 6))
        elif k == "slam":
            w = g["word"].upper()
            if g.get("panel"):
                arr = cv2.GaussianBlur(self.shot(g["shot"], 0.8, 1.5, 1.5, cx=0.3, cy=0.5), (0, 0), 16) * 0.45
                self.comp(arr, self.panel(g["panel"], clamp(p / 0.85)), W / 2, 1330)
            else:
                z = zoom or [1.06, 1.16]
                arr = self.shot(g["shot"], p, z[0], z[1], g.get("cx", 0.5), g.get("cy", 0.42), self.shake(t, g["t0"], 18), warm=g.get("warm", False))
            q = (t - g["t0"]) / 0.14; outer, core = self.slam[w]
            sc = (1.28 - 0.28 * ease(q)) * min(1.0, W * 0.9 / outer.width)
            self.comp(arr, outer, W / 2, H / 2 - 30, sc, clamp(q * 1.4)); self.comp(arr, core, W / 2, H / 2 - 30, sc, clamp(q * 1.4) * 0.9)
        elif k == "payoff":
            z = zoom or [1.06, 1.14]
            arr = self.shot(g["shot"], p, z[0], z[1], g.get("cx", 0.5), g.get("cy", 0.42), warm=g.get("warm", True), contrast=1.06)
            if g.get("sub"):
                self.subtitle(arr, g["sub"], self.fade(t, g, 0.3))
        elif k == "flash":
            arr = np.ones((H, W, 3), np.float32) * np.array(self.acc, np.float32) * (1 - 0.6 * p) + 255 * max(0, 0.5 - p)
        else:
            arr = np.ones((H, W, 3), np.float32) * np.array(BASE, np.float32)
            glow = np.exp(-(((self.xx - W / 2) / 520) ** 2 + ((self.yy - 860) / 640) ** 2))[..., None] * (np.array(self.acc, np.float32) * 0.3)
            arr += glow * (0.8 + 0.2 * np.sin(t * 2))
            self.embers(arr, t, 0.6)
            self.comp(arr, self.end, W / 2, H / 2, 1.03 - 0.03 * ease((t - g["t0"]) / 0.5), clamp((t - g["t0"]) * 3))
        for c in self.cuts:
            if 0 <= t - c < 2 / FPS:
                arr = arr * 1.18 + 8
        arr = arr * self.vig + self.grain[i % 8]
        if t > self.dur - 0.5:
            arr *= clamp((self.dur - t) / 0.5)
        return np.clip(arr, 0, 255).astype(np.uint8)

    # ---------- score ----------
    def audio(self, path):
        SR = 44100; D = self.dur; n = int(SR * D); a = np.zeros(n); tt = np.arange(n) / SR; r = np.random.default_rng(11)
        def seg(t0, d):
            i0 = int(t0 * SR); m = max(0, min(n - i0, int(d * SR))); return i0, m, np.arange(m) / SR
        def boom(t0, amp=1.0):
            i0, m, x = seg(t0, 2.2); f = 38 + 110 * np.exp(-x * 9)
            s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 1.8)
            nz = np.convolve(r.normal(0, 1, m), np.ones(18) / 18, "same") * np.exp(-x * 14)
            a[i0:i0 + m] += amp * (0.95 * s + 0.55 * nz)
        def braam(t0, root=43.65, amp=0.5, d=2.4):
            i0, m, x = seg(t0, d); s = np.zeros(m)
            for mult in (1, 1.5, 2, 2.997, 4):
                for det in (-0.6, 0, 0.7):
                    ph = 2 * np.pi * (root * mult + det) * x
                    s += sum(np.sin(k * ph) / k for k in range(1, 7)) / mult
            a[i0:i0 + m] += amp * np.tanh(s * 0.25) * np.clip(x / 0.04, 0, 1) * np.exp(-x * 1.1)
        def riser(t0, t1, amp=0.25):
            if t1 <= t0:
                return
            i0, m, x = seg(t0, t1 - t0); p = x / (t1 - t0); nz = r.normal(0, 1, m)
            hp = nz - np.convolve(nz, np.ones(4) / 4, "same")
            a[i0:i0 + m] += amp * (0.5 * hp + 0.4 * np.sin(2 * np.pi * np.cumsum(200 + 1600 * p ** 2) / SR)) * p ** 2.2
        def tick(t0, amp=0.18):
            i0, m, x = seg(t0, 0.05); a[i0:i0 + m] += amp * np.sin(2 * np.pi * 2600 * x) * np.exp(-x * 120)
        def thump(t0, amp=0.5):
            i0, m, x = seg(t0, 0.4); a[i0:i0 + m] += amp * np.sin(2 * np.pi * np.cumsum(50 + 60 * np.exp(-x * 30)) / SR) * np.exp(-x * 9)
        def drone(t0, t1, freqs, amp):
            i0, m, x = seg(t0, t1 - t0)
            s = sum(np.sin(2 * np.pi * f * x + 0.3 * np.sin(2 * np.pi * 0.2 * x + k)) for k, f in enumerate(freqs)) / len(freqs)
            a[i0:i0 + m] += amp * s * np.clip(x / 0.5, 0, 1) * np.clip(((t1 - t0) - x) / 0.4, 0, 1)
        def blip(t0, f, amp=0.12, d=0.12):
            i0, m, x = seg(t0, d); a[i0:i0 + m] += amp * np.sin(2 * np.pi * f * x) * np.exp(-x * 30)
        def clang(t0, amp=0.22):
            i0, m, x = seg(t0, 1.2); a[i0:i0 + m] += amp * sum(np.sin(2 * np.pi * f * x) for f in (523, 1371, 2219, 3010)) / 4 * np.exp(-x * 4)
        S = {}
        for g in self.segs:
            S.setdefault(g["kind"], []).append(g)
        op = S["open"][0]; drone(0, op["t1"], (41.2, 61.7, 82.4), 0.16)
        hit = op.get("hit", 1.05); riser(0.1, hit, 0.22); boom(hit, 1.0); clang(hit, 0.25)
        ti = S["title"][0]["t0"]; boom(ti, 0.9); braam(ti, 43.65, 0.55, 2.0)
        mids = [g for g in self.segs if g["kind"] in ("scene", "card")]
        if mids:
            m0, m1 = mids[0]["t0"], mids[-1]["t1"]
            drone(m0, m1, (55, 82.4, 103.8, 164.8), 0.10)
            for k, tb in enumerate(np.arange(m0, m1, 0.5)):
                thump(tb, 0.42 if k % 2 == 0 else 0.22); tick(tb + 0.25)
            for g in mids:
                boom(g["t0"], 0.35)
                if g["kind"] == "card":
                    rows = len(g["card"].get("rows", [])); dur = g["t1"] - g["t0"]
                    for j in range(rows):
                        tf = g["t0"] + 0.35 + j * (dur - 0.6) / max(1, rows); blip(tf, 880, 0.16, 0.25); blip(tf + 0.04, 1320, 0.1, 0.2)
            riser(mids[-1]["t0"], m1, 0.3)
        for j, g in enumerate(S["slam"]):
            boom(g["t0"], 1.0); braam(g["t0"], 49.0 if j == 1 else 43.65, 0.5, 1.4)
            if g.get("panel"):
                for q in range(len(g["panel"].get("steps", []))):
                    blip(g["t0"] + 0.05 + 0.3 * q, 1567, 0.1, 0.15)
        cb = S["callback"][0]; riser(S["slam"][-1]["t0"] + 0.1, cb.get("hit", cb["t0"] + 0.35), 0.28)
        boom(cb.get("hit", cb["t0"] + 0.35), 1.0); clang(cb.get("hit", cb["t0"] + 0.35), 0.3)
        p0, p1 = S["payoff"][0]["t0"], S["payoff"][-1]["t1"]
        drone(p0, p1, (130.8, 164.8, 196, 261.6), 0.13)
        for tb in np.arange(p0, p1, 0.43):
            thump(tb, 0.35); tick(tb + 0.215, 0.08)
        riser(p1 - 1.0, p1, 0.3)
        fl = S["flash"][0]["t0"]; boom(fl, 1.1); braam(fl, 65.4, 0.45, 2.6)
        drone(fl + 0.3, D, (65.4, 98, 130.8, 196), 0.10)
        ir_n = int(SR * 1.6); ir = r.normal(0, 1, ir_n) * np.exp(-np.arange(ir_n) / SR * 4.2); ir[0] = 0
        mix = a + np.fft.irfft(np.fft.rfft(a, 2 * n) * np.fft.rfft(ir, 2 * n))[:n] * 0.012
        mix *= np.clip((D - tt) / 0.6, 0, 1); mix = np.tanh(mix * 1.2); mix = mix / max(1e-6, np.max(np.abs(mix))) * 0.9
        dl = int(SR * 0.011); R = np.concatenate([np.zeros(dl), mix[:-dl]]) * 0.5 + mix * 0.5
        with wave.open(path, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.stack([mix, R], 1) * 32767).astype(np.int16).tobytes())


def _wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if font.getlength(test) <= maxw:
            cur = test
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    return lines


def build(spec, out):
    """Render a trailer item to out (mp4). Returns seconds."""
    clean(spec)
    tr = Trailer(spec)
    wav = os.path.join(tempfile.mkdtemp(prefix="irun-trailer-"), "a.wav"); tr.audio(wav)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-maxrate", "12M", "-bufsize", "24M",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i in range(tr.n):
        p.stdin.write(tr.frame(i).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg failed")
    return tr.dur


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        spec = json.load(f)
    if len(sys.argv) > 3 and sys.argv[3] == "preview":
        tr = Trailer(spec)
        for ts in [float(x) for x in sys.argv[4].split(",")]:
            Image.fromarray(tr.frame(int(round(ts * FPS)))).save(f"{sys.argv[2]}_{ts:.2f}.png")
        print("seconds", tr.dur)
    else:
        print(json.dumps({"out": sys.argv[2], "seconds": build(spec, sys.argv[2])}))
