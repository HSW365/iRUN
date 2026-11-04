"""iRun SERIES engine — 60-second motion-comic episodes (HOODSTARWORLD: THE JOURNEY and any other series).

A different format from engine/trailer.py: cartoon comic art from Canva (engine/canva_shots.py flow), cut into strips
and panels that slam onto a branded stage. Brand is on screen every frame: wordmark top-left, episode bug top-right,
merch ticker at the bottom. Each beat carries a chapter stamp and word-timed captions under a free Kokoro narrator
(engine/narrator.py) over an original boom-bap bed. The last beat is the end card: product, price, QR, next episode.

  python engine/series.py content/series/<slug>.json out/<slug>.mp4

Spec keys:
  pages      {"p1": "content/shots/.../page1.jpg", ...}     source comic pages (2160x3840 Canva exports)
  episode    "01"   title "THE BEGINNING"   series "THE JOURNEY"
  wordmark   ["HOODSTAR", "WORLD"]                           two-tone brand wordmark (white + accent)
  accent     "#f5b301"
  beats      [{"src": "p1", "box": [x0, y0, x1, y1], "dur": 6, "vo": "line", "stamp": "U.S. ARMY",
               "key": ["ARMY"], "title": true}]             box = crop in page fractions
  end        {"src": "p3", "box": [...], "product": "SURVIVOR COLLECTION", "price": "$120",
              "tag": "ONE OF ONE", "cta": "SCAN TO SHOP", "link": "https://...", "next": "EP.02  THE SOLDIER",
              "vo": "line", "dur": 7}
  ticker     "SURVIVOR COLLECTION  ·  1 OF 1  ·  $120  ·  HSW365.CO"
"""
import json
import math
import os
import random
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
FONTS = os.path.join(ROOT, "assets", "fonts")
W, H, FPS = 1080, 1920, 30
SR = 44100
INK = (10, 10, 15)


def F(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


XB = lambda s: F("BarlowCondensed-ExtraBold.ttf", s)  # noqa: E731
SB = lambda s: F("BarlowCondensed-SemiBold.ttf", s)  # noqa: E731
MONO = lambda s: F("SpaceMono-Bold.ttf", s)  # noqa: E731


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x, k=1.70158):
    x = clamp(x) - 1
    return 1 + (k + 1) * x ** 3 + k * x ** 2


def ease_in(x):
    x = clamp(x)
    return x ** 3


# ---------------------------------------------------------------------------------------------------- brand pieces

def wordmark(parts, accent, size=86, stroke=0):
    a, b = parts
    f = XB(size)
    wa = f.getlength(a); wb = f.getlength(b)
    im = Image.new("RGBA", (int(wa + wb) + 12, int(size * 1.15)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((4, 0), a, font=f, fill=(255, 255, 255), stroke_width=stroke, stroke_fill=INK)
    d.text((4 + wa, 0), b, font=f, fill=accent, stroke_width=stroke, stroke_fill=INK)
    return im.crop(im.getbbox())


def shadow(im, r=18, a=170, off=(0, 14)):
    pad = r * 3
    s = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    m = im.split()[3].point(lambda v: a if v else 0)
    s.paste((0, 0, 0, 255), (pad + off[0], pad + off[1]), m)
    s = s.filter(ImageFilter.GaussianBlur(r))
    s.alpha_composite(im, (pad, pad))
    return s, pad


def comic_frame(img, accent):
    """Panel border: thin accent keyline, white gutter, heavy ink outline."""
    b1, b2, b3 = 4, 10, 8
    w, h = img.width + 2 * (b1 + b2 + b3), img.height + 2 * (b1 + b2 + b3)
    out = Image.new("RGBA", (w, h), INK + (255,))
    d = ImageDraw.Draw(out)
    d.rectangle([b3, b3, w - b3 - 1, h - b3 - 1], fill=(255, 255, 255, 255))
    d.rectangle([b3 + b2, b3 + b2, w - b3 - b2 - 1, h - b3 - b2 - 1], fill=accent + (255,))
    out.paste(img.convert("RGB"), (b1 + b2 + b3, b1 + b2 + b3))
    return out


def stamp(text, accent, size=78):
    f = XB(size)
    tw = f.getlength(text)
    pw, ph = int(tw + 64), int(size * 1.35)
    im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, pw - 1, ph - 1], fill=accent + (255,))
    d.rectangle([7, 7, pw - 8, ph - 8], outline=INK + (255,), width=5)
    d.text((32, ph / 2), text, font=f, fill=INK, anchor="lm")
    # rubber-stamp wear
    rnd = random.Random(len(text))
    px = im.load()
    for _ in range(int(pw * ph * 0.012)):
        x, y = rnd.randrange(pw), rnd.randrange(ph)
        r, g, b, a = px[x, y]
        px[x, y] = (r, g, b, int(a * 0.25))
    return im.rotate(-4, resample=Image.BICUBIC, expand=True)


def halftone(accent, alpha=26, step=26):
    im = Image.new("RGBA", (W + step * 2, H + step * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for yi, y in enumerate(range(0, H + step * 2, step)):
        for x in range(((yi % 2) * step) // 2, W + step * 2, step):
            r = 2 + 3.5 * (y / (H + step))
            d.ellipse([x - r, y - r, x + r, y + r], fill=accent + (alpha,))
    return im


def qr_img(url, size):
    import segno, io
    buf = io.BytesIO()
    segno.make(url, error="h").save(buf, kind="png", scale=20, border=2, dark="#0a0a0f", light="#ffffff")
    return Image.open(buf).convert("RGBA").resize((size, size), Image.NEAREST)


# ---------------------------------------------------------------------------------------------------- the episode

class Episode:
    def __init__(self, spec):
        self.s = spec
        self.accent = hexrgb(spec.get("accent", "#f5b301"))
        self.pages = {k: Image.open(os.path.join(ROOT, v)).convert("RGB") for k, v in spec["pages"].items()}
        self.beats = list(spec["beats"])
        end = dict(spec["end"]); end["is_end"] = True
        self.beats.append(end)
        t = 0.0
        for b in self.beats:
            b["t0"] = t; t += float(b["dur"]); b["t1"] = t
        self.T = t
        self.N = int(round(self.T * FPS))
        self._static()

    def crop(self, src, box):
        p = self.pages[src]
        x0, y0, x1, y1 = box
        c = p.crop((int(x0 * p.width), int(y0 * p.height), int(x1 * p.width), int(y1 * p.height)))
        return c

    def _static(self):
        A = self.accent
        self.bg_dots = halftone(A)
        self.logo = wordmark(self.s.get("wordmark", ["HOODSTAR", "WORLD"]), A, 92, stroke=0)
        epf = XB(44)
        ep = f"{self.s.get('series', 'THE JOURNEY')}  ·  EP.{self.s['episode']}"
        bug = Image.new("RGBA", (int(epf.getlength(ep)) + 40, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(bug)
        d.rounded_rectangle([0, 0, bug.width - 1, 63], radius=8, outline=A + (255,), width=3)
        d.text((20, 32), ep, font=epf, fill=(255, 255, 255), anchor="lm")
        self.bug = bug
        # ticker strip
        tk = self.s.get("ticker", "")
        tf = XB(40)
        unit = f"   {tk}   ·"
        self.tick_w = int(tf.getlength(unit))
        strip = Image.new("RGBA", (self.tick_w * 4, 70), A + (255,))
        d = ImageDraw.Draw(strip)
        for i in range(4):
            d.text((i * self.tick_w, 35), unit, font=tf, fill=INK, anchor="lm")
        self.ticker = strip
        # per-beat assets
        for b in self.beats:
            art = self.crop(b["src"], b["box"])
            if b.get("is_end"):
                bg = art.resize((W, int(art.height * W / art.width)), Image.LANCZOS)
                b["back"] = self._backdrop(art, dark=0.28, blur=22)
                b["panel"] = None
                self._end_assets(b)
                continue
            maxw, maxh = W - 70, 1000
            sc = min(maxw / art.width, maxh / art.height)
            art = art.resize((int(art.width * sc), int(art.height * sc)), Image.LANCZOS)
            art = art.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
            fr = comic_frame(art, A)
            b["panel"], b["pad"] = shadow(fr)
            b["_ph"] = fr.height; b["_y0"] = 200 + max(0, (1560 - (fr.height + 360)) / 2)
            b["_sy"] = b["_y0"] + fr.height + 95
            b["_cy"] = b["_sy"] + 150
            b["back"] = self._backdrop(art, dark=0.42, blur=28)
            b["stamp"] = stamp(b["stamp"], A) if b.get("stamp") else None
            b["words"] = (b["caption"] if "caption" in b else b.get("vo", "")).split()

    def _backdrop(self, art, dark, blur):
        sc = max((W + 120) / art.width, (H + 120) / art.height)
        im = art.resize((int(art.width * sc), int(art.height * sc)), Image.BILINEAR)
        im = im.filter(ImageFilter.GaussianBlur(blur))
        im = Image.blend(Image.new("RGB", im.size, INK), im, dark)
        return im

    def _end_assets(self, b):
        A = self.accent
        b["e_logo"] = wordmark(self.s.get("wordmark", ["HOODSTAR", "WORLD"]), A, 132)
        prod = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(prod)
        d.text((W / 2, 52), b["product"], font=XB(96), fill=(255, 255, 255), anchor="mm")
        d.text((W / 2, 148), f"{b['tag']}  ·  {b['price']}", font=XB(84), fill=A, anchor="mm")
        b["e_prod"] = prod
        ph = b.get("photo")
        b["e_photo"] = None
        if ph:
            im = Image.open(os.path.join(ROOT, ph)).convert("RGB")
            side = min(im.size); im = im.crop(((im.width - side) // 2, (im.height - side) // 2,
                                                (im.width + side) // 2, (im.height + side) // 2)).resize((560, 560), Image.LANCZOS)
            b["e_photo"], b["e_ppad"] = shadow(comic_frame(im, A))
        q = qr_img(b["link"], 250)
        card = Image.new("RGB", (290, 340), (255, 255, 255))
        d = ImageDraw.Draw(card)
        card.paste(q, (20, 18), q)
        d.text((145, 305), b["cta"], font=XB(40), fill=INK, anchor="mm")
        b["e_qr"], b["e_qpad"] = shadow(comic_frame(card, A))
        nx = Image.new("RGBA", (W, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(nx)
        d.text((W / 2, 40), f"NEXT EPISODE   {b['next']}", font=XB(54), fill=(255, 255, 255), anchor="mm")
        b["e_next"] = nx

    def _end(self, fr, b, lt):
        A = self.accent
        k = ease_back(lt / 0.5, 1.6)
        lg = b["e_logo"]; s = 0.6 + 0.4 * k
        l2 = lg.resize((max(1, int(lg.width * s)), max(1, int(lg.height * s))), Image.BICUBIC)
        fr.alpha_composite(l2, (int(W / 2 - l2.width / 2), int(250 - l2.height / 2 + 40)))
        if b["e_photo"] is not None and lt > 0.3:
            k2 = ease_back((lt - 0.3) / 0.5, 1.5)
            p = b["e_photo"]; s2 = 0.7 + 0.3 * k2
            p2 = p.resize((int(p.width * s2), int(p.height * s2)), Image.BICUBIC).rotate(-2.5 * k2, resample=Image.BICUBIC, expand=True)
            fr.alpha_composite(p2, (int(W / 2 - p2.width / 2), int(700 - p2.height / 2)))
        if lt > 0.7:
            a = ease_out((lt - 0.7) / 0.4)
            pr = b["e_prod"].copy(); pr.putalpha(pr.split()[3].point(lambda v: int(v * a)))
            fr.alpha_composite(pr, (0, int(1030 + 30 * (1 - a))))
        if lt > 1.1:
            k3 = ease_back((lt - 1.1) / 0.45, 1.5)
            q = b["e_qr"]; s3 = 0.5 + 0.5 * k3
            q2 = q.resize((max(1, int(q.width * s3)), max(1, int(q.height * s3))), Image.BICUBIC)
            fr.alpha_composite(q2, (int(W / 2 - q2.width / 2), int(1450 - q2.height / 2)))
        if lt > 1.7:
            fr.alpha_composite(b["e_next"], (0, 1670))
        b.setdefault("words", [])

    # ------------------------------------------------------------------------------------------------ captions
    def caption(self, frame, b, lt):
        words = b["words"]
        if not words:
            return
        vo_d = b.get("vo_dur", b["dur"] - 0.8)
        start = 0.25
        n = len(words)
        shown = int(clamp((lt - start) / max(vo_d, 0.5)) * n + 0.999) if lt > start else 0
        if shown <= 0:
            return
        keys = {k.upper().strip(".,!?") for k in b.get("key", [])}
        f = XB(84)
        lines, cur = [], []
        for w in words[:shown]:
            test = " ".join(cur + [w])
            if f.getlength(test.upper()) > W - 150 and cur:
                lines.append(cur); cur = [w]
            else:
                cur.append(w)
        lines.append(cur)
        lines = lines[-2:]
        y = b.get("_cy", 1500)
        d = ImageDraw.Draw(frame)
        for ln in lines:
            txt = " ".join(ln).upper()
            x = (W - f.getlength(txt)) / 2
            for w in ln:
                wu = w.upper()
                col = self.accent if wu.strip(".,!?'") in keys else (255, 255, 255)
                d.text((x, y), wu, font=f, fill=col, stroke_width=7, stroke_fill=INK, anchor="lm")
                x += f.getlength(wu + " ")
            y += 92

    # ------------------------------------------------------------------------------------------------ frame
    def frame(self, i):
        t = i / FPS
        b = next(x for x in self.beats if x["t0"] <= t < x["t1"]) if t < self.T else self.beats[-1]
        lt = t - b["t0"]
        A = self.accent
        # backdrop with slow push
        bk = b["back"]
        z = lt / b["dur"]
        ox = int((bk.width - W) * (0.5 + 0.1 * math.sin(z * 2))); oy = int((bk.height - H) * (0.3 + 0.4 * z))
        fr = bk.crop((ox, oy, ox + W, oy + H)).convert("RGBA")
        dots = self.bg_dots
        dy = int((t * 18) % 26)
        fr.alpha_composite(dots.crop((0, dy, W, dy + H)))

        if b.get("is_end"):
            self._end(fr, b, lt)
        else:
            self._beat(fr, b, lt, t)

        # persistent brand chrome
        top = Image.new("RGBA", (W, 190), (0, 0, 0, 0))
        g = np.linspace(215, 0, 190).astype(np.uint8)
        top.putalpha(Image.fromarray(np.repeat(g[:, None], W, 1)))
        fr.alpha_composite(Image.new("RGBA", (W, 190), INK + (0,)))
        fr.alpha_composite(Image.composite(Image.new("RGBA", (W, 190), INK + (255,)), Image.new("RGBA", (W, 190), (0, 0, 0, 0)), top.split()[3]))
        lg = self.logo
        fr.alpha_composite(lg, (44, 52))
        fr.alpha_composite(self.bug, (W - self.bug.width - 40, 62))
        # ticker
        tx = int((t * 140) % self.tick_w)
        fr.alpha_composite(self.ticker.crop((tx, 0, tx + W, 70)), (0, H - 112))
        # transition flash
        for bb in self.beats[1:]:
            dt = t - bb["t0"]
            if 0 <= dt < 0.18:
                a = int(255 * (1 - dt / 0.18) * 0.85)
                fr.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, a)))
        # film grain
        return fr.convert("RGB")

    def _beat(self, fr, b, lt, t):
        A = self.accent
        p, pad = b["panel"], b["pad"]
        enter = ease_back(lt / 0.55, 1.4)
        exit_ = ease_in((lt - (b["dur"] - 0.3)) / 0.3)
        side = -1 if self.beats.index(b) % 2 else 1
        sc = 0.86 + 0.14 * enter + 0.035 * (lt / b["dur"])
        rot = side * (2.2 * (1 - enter) + 0.9)
        im = p.resize((int(p.width * sc), int(p.height * sc)), Image.BICUBIC).rotate(rot, resample=Image.BICUBIC, expand=True)
        cx = W / 2 + side * (1 - clamp(lt / 0.45)) * 900 - side * exit_ * 1100
        cy = b["_y0"] + b["_ph"] / 2 + 20
        fr.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))
        # title slam on the first beat
        if b.get("title"):
            self._title(fr, b, lt)
        # chapter stamp
        st = b.get("stamp")
        if st is not None and lt > 0.5:
            k = ease_back((lt - 0.5) / 0.35, 2.2)
            s2 = st.resize((max(1, int(st.width * (2.4 - 1.4 * k))), max(1, int(st.height * (2.4 - 1.4 * k)))), Image.BICUBIC)
            a = clamp((lt - 0.5) / 0.15)
            if a < 1:
                s2.putalpha(s2.split()[3].point(lambda v: int(v * a)))
            x = 70 if side > 0 else W - 70 - s2.width
            fr.alpha_composite(s2, (int(x), int(b["_sy"] - s2.height / 2)))
        self.caption(fr, b, lt)

    def _title(self, fr, b, lt):
        A = self.accent
        if lt > b["dur"] - 0.2:
            return
        d = ImageDraw.Draw(fr)
        k = ease_back((lt - 1.0) / 0.4, 1.8)
        if lt > 1.0:
            f = XB(int(150 * (1.6 - 0.6 * k)))
            d.text((W / 2, b['_sy'] + 20), self.s.get("series", "THE JOURNEY"), font=f, fill=(255, 255, 255), stroke_width=10, stroke_fill=INK, anchor="mm")
        if lt > 1.6:
            k2 = ease_out((lt - 1.6) / 0.3)
            f2 = XB(64)
            txt = f"EPISODE {int(self.s['episode'])}  ·  {self.s['title']}"
            w = f2.getlength(txt) + 60
            x0 = W / 2 - w / 2
            yb = b['_sy'] + 110
            d.rectangle([x0, yb, x0 + w * k2, yb + 82], fill=A)
            if k2 > 0.9:
                d.text((W / 2, yb + 41), txt, font=f2, fill=INK, anchor="mm")

    # ------------------------------------------------------------------------------------------------ audio
    def audio(self, path, vo_files):
        n = int(self.T * SR) + SR
        mix = np.zeros(n, np.float32)
        bpm = 88.0; beat = 60 / bpm
        rnd = np.random.default_rng(365)
        t_ = lambda d: np.arange(int(d * SR)) / SR  # noqa: E731

        def add(sig, t0, g=1.0):
            i = int(t0 * SR)
            if i >= n:
                return
            e = min(n, i + len(sig)); mix[i:e] += sig[: e - i] * g

        tk = t_(0.45)
        kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-tk * 28)) * tk) * np.exp(-tk * 7)
        ts = t_(0.25)
        snare = (rnd.standard_normal(len(ts)) * 0.7 + np.sin(2 * np.pi * 190 * ts) * 0.5) * np.exp(-ts * 18)
        th = t_(0.06)
        hat = rnd.standard_normal(len(th)) * np.exp(-th * 70)
        hat = np.diff(hat, prepend=0)
        # minor chord stabs (Am - F - C - G feel, dark keys)
        chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 246.94, 293.66], [164.81, 207.65, 246.94]]
        bars = int(self.T / (beat * 4)) + 2
        start = self.beats[0].get("music_in", 0.0)
        for bar in range(bars):
            b0 = start + bar * beat * 4
            ch = chords[bar % 4]
            td = t_(beat * 4)
            pad = sum(np.sin(2 * np.pi * f * td) + 0.3 * np.sin(2 * np.pi * f * 2.002 * td) for f in ch)
            pad *= (1 - np.exp(-td * 6)) * np.exp(-td * 0.55) * 0.06
            add(pad.astype(np.float32), b0)
            bass_f = ch[0] / 4
            tb = t_(beat * 1.6)
            bass = np.tanh(2.2 * np.sin(2 * np.pi * bass_f * tb)) * np.exp(-tb * 1.6) * 0.22
            add(bass.astype(np.float32), b0); add(bass.astype(np.float32), b0 + beat * 2.5, 0.8)
            for k_ in (0, 1.75, 2.5):
                add(kick.astype(np.float32), b0 + k_ * beat, 0.9)
            for s_ in (1, 3):
                add(snare.astype(np.float32), b0 + s_ * beat, 0.38)
            for h_ in range(8):
                sw = 0.04 if h_ % 2 else 0.0
                add(hat.astype(np.float32), b0 + (h_ * 0.5 + sw) * beat, 0.09 if h_ % 2 else 0.14)
        # impact hits on every cut
        ti = t_(1.6)
        boom = np.sin(2 * np.pi * (38 + 60 * np.exp(-ti * 6)) * ti) * np.exp(-ti * 2.4) * 0.6
        for bb in self.beats:
            add(boom.astype(np.float32), bb["t0"], 0.7 if bb is not self.beats[0] else 1.0)
        # end-card riser fade
        e0 = self.beats[-1]["t0"]
        # voice + ducking
        vo = np.zeros(n, np.float32)
        import soundfile as sf
        for bb, fpath in zip(self.beats, vo_files):
            if not fpath:
                continue
            a, sr = sf.read(fpath, dtype="float32")
            if a.ndim > 1:
                a = a.mean(1)
            i = int((bb["t0"] + 0.25) * SR); e = min(n, i + len(a))
            vo[i:e] += a[: e - i]
        env = np.convolve((np.abs(vo) > 0.02).astype(np.float32), np.ones(int(SR * 0.25)) / int(SR * 0.25), "same")
        duck = 1 - 0.55 * np.clip(env * 3, 0, 1)
        out = mix * duck + vo * 1.05
        fade = np.ones(n, np.float32)
        fl = int(1.2 * SR); endi = int(self.T * SR)
        fade[endi - fl:endi] = np.linspace(1, 0, fl); fade[endi:] = 0
        out *= fade
        out = np.tanh(out * 1.2) * 0.92
        sf.write(path, out[: endi], SR)


def narrate(ep, slug):
    """Kokoro narrator (free). One wav per beat with a vo line; stores each line's length on the beat."""
    lines = [b.get("vo", "") for b in ep.beats]
    outdir = os.path.join(ROOT, "assets", "voice", slug)
    todo = [(i, l) for i, l in enumerate(lines) if l]
    sys.path.insert(0, HERE)
    import narrator
    os.environ["IRUN_NARRATOR"] = "kokoro"  # series narrator is always the free in-house voice (no ElevenLabs)
    narrator.main(outdir, [l for _, l in todo], speed=float(ep.s.get("vo_speed", 0.9)))
    files = [None] * len(lines)
    import soundfile as sf
    for k, (i, _) in enumerate(todo, 1):
        p = os.path.join(outdir, f"vo{k}.wav")
        files[i] = p
        info = sf.info(p)
        ep.beats[i]["vo_dur"] = info.frames / info.samplerate
        if ep.beats[i]["vo_dur"] > ep.beats[i]["dur"] - 0.5:
            print(f"[series] warn: beat {i} vo {ep.beats[i]['vo_dur']:.1f}s > beat {ep.beats[i]['dur']}s")
    return files


def build(spec, out, slug=None):
    slug = slug or os.path.splitext(os.path.basename(out))[0]
    ep = Episode(spec)
    files = narrate(ep, slug)
    tmp = tempfile.mkdtemp()
    wav = os.path.join(tmp, "mix.wav")
    ep.audio(wav, files)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                         stdin=subprocess.PIPE)
    for i in range(ep.N):
        p.stdin.write(ep.frame(i).tobytes())
        if i % 150 == 0:
            print(f"[series] frame {i}/{ep.N}", flush=True)
    p.stdin.close(); p.wait()
    if p.returncode:
        raise RuntimeError("ffmpeg failed")
    print(f"[series] {out}  {ep.T:.1f}s")
    return ep.T


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        build(json.load(f), sys.argv[2])
