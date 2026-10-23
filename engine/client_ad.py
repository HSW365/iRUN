"""Client brand ads: a cinematic, scene-based vertical commercial in the client's own brand (1080x1920, 30fps).

Unlike render.py (kinetic text) or flyer.video (a still flyer), this draws every frame: full-bleed job photos with
slow camera moves, a logo sting, numbered trade scenes, a counting proof scene, a credits roll and an end card,
joined by a brand-colored wipe, with grain, vignette and a synthesized score ducked under the voiceover.

A queue item opts in with "ad": "<id in ADS>". Its "beats" are the voiceover lines, one per scene, in order.
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), "..")
CLIENTS = os.path.join(ROOT, "assets", "clients")
W, H, FPS = 1080, 1920, 30
M = 84


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


NEWARK_AD = {
    "brand": "newark",
    "colors": {"bg": "#06182b", "bg2": "#0b2a4a", "accent": "#c4161c", "accent2": "#2f7de1",
               "ink": "#ffffff", "soft": "#c9d4e2", "mute": "#7f91a8", "line": "#1f3d61"},
    "fonts": {"display": "big-shoulders.woff2", "body": "libre-franklin.woff2"},
    "name": "NEW ARK",
    "tagline": "PLUMBING  ·  HEATING  ·  AIR CONDITIONING",
    "scenes": [
        {"type": "logo"},
        {"type": "statement", "photo": "hero.webp", "kicker": "PHILLIPSBURG, NEW JERSEY",
         "lines": ["ON TIME.", "ON BUDGET.", "ON SPEC."]},
        {"type": "trade", "photo": "plumbing.webp", "n": "01", "title": ["PLUMBING"],
         "items": ["Kitchens & bathrooms", "Water heaters", "Drain & sewer lines"]},
        {"type": "trade", "photo": "hvac.webp", "n": "02", "title": ["HEATING &", "AIR CONDITIONING"],
         "items": ["Furnaces & boilers", "Duct systems", "Design & install"]},
        {"type": "trade", "photo": "geo.webp", "n": "03", "title": ["GEOTHERMAL"],
         "items": ["Heat & cool from the earth", "Clean energy", "Lower bills"]},
        {"type": "trade", "photo": "fire.webp", "n": "04", "title": ["FIRE", "PROTECTION"],
         "items": ["Sprinkler systems", "Designed & installed", "Inspected to NFPA"]},
        {"type": "proof", "count": 40, "label": ["YEARS IN", "THE TRADE"],
         "lines": ["NJ MASTER PLUMBER  #36BI00464600", "NJ HVAC CONTRACTOR  #19HC00178300",
                   "NJ FIRE SPRINKLER  #P01631", "LICENSED  ·  INSURED  ·  UNION & OPEN SHOP"]},
        {"type": "credits", "kicker": "TRUSTED ON",
         "lines": ["BENIHANA  ·  SHORT HILLS", "NEWARK ACCESS STATION", "JOINT MEETING  ·  ELIZABETH",
                   "COLAS  ·  MORRISTOWN", "SCHOOLS  ·  HOSPITALS", "HOMES ACROSS NORTH JERSEY"]},
        {"type": "statement", "photo": "hero.webp", "kicker": "NO CHARGE. NO PRESSURE.",
         "lines": ["FREE", "ESTIMATES."], "sub": "Every job priced by the owner himself."},
        {"type": "end", "url": "ARK-HVAC.COM", "cta": "GET YOUR FREE ESTIMATE",
         "alt": "Message 24/7  ·  908-454-4043", "foot": "412 Firth St, Phillipsburg, NJ  ·  Serving North Jersey"},
    ],
}
HSW_MASK_AD = {
    "brand": "hsw365-ledmask",
    "grade": "none",
    "colors": {"bg": "#070506", "bg2": "#1a0709", "accent": "#ff2a36", "accent2": "#b3121c",
               "ink": "#ffffff", "soft": "#e6d4d2", "mute": "#9a8784", "line": "#3a1a1c"},
    "fonts": {"display": "big-shoulders.woff2", "body": "libre-franklin.woff2"},
    "name": "HSW365",
    "tagline": "LED PHOTON MASK  ·  RED + INFRARED",
    "hud_sub": "LED PHOTON MASK",
    "hud_url": "HSW365.CO",
    "index_label": "FEATURE",
    "index_total": "03",
    "button": "SHOP NOW",
    "license": "Cosmetic skincare device  ·  Not a medical treatment",
    "scenes": [
        {"type": "logo"},
        {"type": "statement", "photo": "hero.png", "kicker": "THE SPA, AT HOME",
         "lines": ["YOUR GLOW.", "ON DEMAND."]},
        {"type": "trade", "photo": "face.png", "n": "01", "title": ["FULL FACE", "+ NECK"],
         "items": ["Forehead to collarbone", "Flexible, contoured fit", "Even light, edge to edge"]},
        {"type": "trade", "photo": "glow.png", "n": "02", "title": ["RED +", "INFRARED"],
         "items": ["Multiple light modes", "Adjustable levels", "Hands-free sessions"]},
        {"type": "trade", "photo": "control.png", "n": "03", "title": ["WIRELESS"],
         "items": ["Magnetic snap-on controller", "USB rechargeable", "Use it anywhere"]},
        {"type": "statement", "photo": "hero2.png", "kicker": "RELAX. PRESS PLAY.",
         "lines": ["SELF-CARE", "SIMPLIFIED."], "sub": "A few minutes a day. Your routine, upgraded."},
        {"type": "end", "url": "HSW365.CO", "cta": "LED PHOTON MASK  ·  $299",
         "alt": "Link in bio  ·  Ships to your door", "foot": "HSW365  ·  Turn Negative Into Positive"},
    ],
}
ADS = {"newark-premium": NEWARK_AD, "hsw365-ledmask": HSW_MASK_AD}


# ---------- easing ----------
def _clamp(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out(x):
    x = _clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = _clamp(x)
    return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


class _Fonts:
    def __init__(self, folder, files):
        self.folder, self.files, self.cache = folder, files, {}

    def __call__(self, kind, size, weight):
        key = (kind, int(size), weight)
        if key not in self.cache:
            f = ImageFont.truetype(os.path.join(self.folder, self.files[kind]), int(size))
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
            self.cache[key] = f
        return self.cache[key]


class Ad:
    def __init__(self, spec):
        self.s = spec
        self.c = {k: _rgb(v) for k, v in spec["colors"].items()}
        self.dir = os.path.join(CLIENTS, spec["brand"])
        self.f = _Fonts(self.dir, spec["fonts"])
        self.photos = {}
        logo = Image.open(os.path.join(self.dir, "logo.webp")).convert("RGBA")
        # key out the flat black card behind the mark so it sits on the brand navy
        arr = np.asarray(logo).astype("float32")
        mx = arr[..., :3].max(axis=2)
        arr[..., 3] = np.clip((mx - 18) / 40, 0, 1) * 255
        self.logo = Image.fromarray(arr.astype("uint8"), "RGBA")
        self._prep_static()

    # ---------- static layers ----------
    def _prep_static(self):
        c = self.c
        base = Image.new("RGB", (W, H), c["bg"])
        top = Image.new("RGB", (W, H), c["bg2"])
        mask = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 - v)
        self.bg = Image.composite(top, base, mask)
        grid = ImageDraw.Draw(self.bg)
        for x in range(0, W, 120):
            grid.line([(x, 0), (x, H)], fill=tuple(min(255, v + 6) for v in c["bg"]), width=1)
        for y in range(0, H, 120):
            grid.line([(0, y), (W, y)], fill=tuple(min(255, v + 6) for v in c["bg"]), width=1)
        # vignette
        v = Image.new("L", (W, H), 0)
        ImageDraw.Draw(v).ellipse([-W * .35, -H * .18, W * 1.35, H * 1.18], fill=255)
        self.vig = v.filter(ImageFilter.GaussianBlur(220))
        self.black = Image.new("RGB", (W, H), (0, 0, 0))
        # grain tiles
        rng = np.random.default_rng(7)
        self.grain = [Image.fromarray(rng.normal(128, 14, (H // 2, W // 2)).clip(0, 255).astype("uint8"))
                      .resize((W, H)) for _ in range(4)]
        # bottom/top photo washes
        g = Image.linear_gradient("L").resize((W, H))  # 0 top -> 255 bottom
        self.wash_bottom = g.point(lambda v: int(255 * (_clamp((v / 255 - .30) / .55) ** 1.4)))
        self.wash_top = g.point(lambda v: int(150 * _clamp(1 - v / 255 / .22)))

    def photo(self, name):
        if name not in self.photos:
            im = Image.open(os.path.join(self.dir, name)).convert("RGB")
            scale = max(W * 1.22 / im.width, H * 1.22 / im.height)
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
            # cool, contrasty grade toward the brand navy
            arr = np.asarray(im).astype("float32")
            lum = arr.mean(axis=2, keepdims=True)
            if self.s.get("grade", "cool") == "cool":
                arr = lum + (arr - lum) * 0.82
                arr = (arr - 128) * 1.12 + 120
                arr[..., 2] += 8
                arr[..., 0] -= 4
            else:  # "none": the photo is already graded (product key art)
                arr = (arr - 128) * 1.04 + 126
            self.photos[name] = Image.fromarray(arr.clip(0, 255).astype("uint8"))
        return self.photos[name]

    def kenburns(self, name, t, direction=1):
        im = self.photo(name)
        z = 1.0 + 0.10 * ease_io(t)
        cw, ch = W / (W * 1.22 / im.width) / z, H / (H * 1.22 / im.height) / z
        cw = min(cw, im.width)
        ch = min(ch, im.height)
        cx = im.width / 2 + direction * (im.width - cw) * 0.35 * (ease_io(t) - .5)
        cy = im.height / 2 - (im.height - ch) * 0.18 * ease_io(t)
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        return im.resize((W, H), Image.BILINEAR, box=box)

    # ---------- text helpers ----------
    def text_in(self, img, xy, text, font, fill, p, rise=70, shadow=True, anchor="la"):
        """Slide-up + fade reveal of one line, p in 0..1."""
        if p <= 0:
            return
        a = ease_out(p)
        d0 = ImageDraw.Draw(img)
        bb = d0.textbbox((0, 0), text, font=font, anchor=anchor)
        w, h = bb[2] - bb[0] + 40, bb[3] - bb[1] + 40
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ox, oy = 20 - bb[0], 20 - bb[1]
        if shadow:
            sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(sh).text((ox, oy + 4), text, font=font, fill=(0, 0, 0, 170), anchor=anchor)
            layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(8)))
            ld = ImageDraw.Draw(layer)
        ld.text((ox, oy), text, font=font, fill=fill + (255,), anchor=anchor)
        if a < 1:
            alpha = layer.split()[3].point(lambda v: int(v * a))
            layer.putalpha(alpha)
        x, y = xy
        img.paste(layer, (int(x - ox), int(y + (1 - a) * rise - oy)), layer)

    def bar(self, img, x, y, w, h, p, color):
        if p <= 0:
            return
        ImageDraw.Draw(img).rectangle([x, y, x + int(w * ease_out(p)), y + h], fill=color)

    def hud(self, img, scene_i, n, t_global):
        c = self.c
        d = ImageDraw.Draw(img)
        lg = self.logo.resize((86, 86), Image.LANCZOS)
        img.paste(lg, (M, 96), lg)
        d.text((M + 104, 104), self.s["name"], font=self.f("display", 44, 800), fill=c["ink"])
        d.text((M + 106, 152), self.s.get("hud_sub", "PHILLIPSBURG, NJ"), font=self.f("body", 22, 600), fill=c["soft"])
        lbl = self.s.get("hud_url", "ARK-HVAC.COM")
        fb = self.f("body", 24, 700)
        d.text((W - M - d.textlength(lbl, font=fb), 122), lbl, font=fb, fill=c["soft"])
        # progress hairline
        d.rectangle([M, H - 150, W - M, H - 147], fill=c["line"])
        d.rectangle([M, H - 150, M + int((W - 2 * M) * t_global), H - 147], fill=c["accent"])

    # ---------- scenes ----------
    def scene(self, sc, t, dur):
        c, f = self.c, self.f
        k = sc["type"]
        fr = t * dur  # seconds into scene
        if k == "logo":
            img = self.bg.copy()
            # light bloom behind logo
            glow = Image.new("RGB", (W, H), (0, 0, 0))
            r = int(380 + 120 * ease_out(t))
            ImageDraw.Draw(glow).ellipse([W / 2 - r, H * .40 - r, W / 2 + r, H * .40 + r], fill=c["accent2"])
            img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), .28 * ease_out(fr / .8))
            s = 0.86 + 0.14 * ease_out(fr / .9)
            size = int(470 * s)
            lg = self.logo.resize((size, size), Image.LANCZOS)
            a = ease_out(fr / .6)
            lg.putalpha(lg.split()[3].point(lambda v: int(v * a)))
            img.paste(lg, (W // 2 - size // 2, int(H * .40) - size // 2), lg)
            # light sweep across the logo
            sw = (fr - .5) / .9
            if 0 < sw < 1:
                streak = Image.new("L", (W, H), 0)
                x = -300 + sw * (W + 600)
                ImageDraw.Draw(streak).polygon([(x, 0), (x + 90, 0), (x - 260, H), (x - 350, H)], fill=110)
                streak = streak.filter(ImageFilter.GaussianBlur(30))
                img = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)), img, streak)
            ft = f("display", 168, 900)
            self.text_in(img, (W / 2, H * .62), self.s["name"], ft, c["ink"], (fr - .35) / .5, anchor="mt")
            self.bar(img, W / 2 - 90, int(H * .62) + 196, 180, 8, (fr - .7) / .4, c["accent"])
            self.text_in(img, (W / 2, H * .62 + 232), self.s["tagline"], f("body", 32, 700), c["soft"],
                         (fr - .85) / .5, rise=30, anchor="mt")
            return img
        if k in ("statement", "trade"):
            img = self.kenburns(sc["photo"], t, 1 if sc.get("n", "01") in ("01", "03") else -1)
            img = Image.composite(Image.new("RGB", (W, H), c["bg"]), img, self.wash_bottom)
            img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, self.wash_top)
        if k == "statement":
            y = int(H * (.56 if sc.get("sub") else .57))
            self.text_in(img, (M, y - 70), sc["kicker"], f("body", 30, 700), c["soft"], fr / .4, rise=24)
            self.bar(img, M, y - 18, 140, 8, (fr - .1) / .4, c["accent"])
            hs = 210 if len(sc["lines"]) <= 2 else 176
            ft = f("display", hs, 900)
            for i, line in enumerate(sc["lines"]):
                col = c["accent"] if i == len(sc["lines"]) - 1 else c["ink"]
                self.text_in(img, (M - 6, y + 20 + i * int(hs * .94)), line, ft, col, (fr - .2 - i * .32) / .45)
            if sc.get("sub"):
                yy = y + 20 + len(sc["lines"]) * int(hs * .94) + 30
                self.text_in(img, (M, yy), sc["sub"], f("body", 40, 500), c["soft"],
                             (fr - .3 - len(sc["lines"]) * .32) / .5, rise=24)
            return img
        if k == "trade":
            y = int(H * .58)
            nf = f("display", 300, 900)
            # big outlined index number
            p = ease_out(fr / .5)
            if p > 0:
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(lay).text((W - M + 20, y - 260), sc["n"], font=nf, anchor="ra",
                                         fill=(0, 0, 0, 0), stroke_width=3,
                                         stroke_fill=c["accent"] + (int(230 * p),))
                img.paste(lay, (0, int((1 - p) * 60)), lay)
            self.text_in(img, (M, y - 40), f"{self.s.get('index_label', 'SERVICE')} {sc['n']} / {self.s.get('index_total', '04')}", f("body", 28, 700), c["soft"], fr / .35, rise=20)
            self.bar(img, M, y + 4, 120, 8, (fr - .1) / .4, c["accent"])
            ts = 168 if max(len(x) for x in sc["title"]) <= 10 else 118
            ft = f("display", ts, 900)
            yy = y + 36
            for i, line in enumerate(sc["title"]):
                self.text_in(img, (M - 4, yy), line, ft, c["ink"], (fr - .15 - i * .18) / .42)
                yy += int(ts * .95)
            yy += 34
            fb = f("body", 40, 600)
            for i, it in enumerate(sc["items"]):
                pp = (fr - .55 - i * .18) / .4
                if pp > 0:
                    d = ImageDraw.Draw(img)
                    d.rectangle([M, yy + 22, M + int(22 * ease_out(pp)), yy + 26], fill=c["accent"])
                self.text_in(img, (M + 44, yy), it, fb, c["soft"], pp, rise=18)
                yy += 66
            return img
        if k == "proof":
            img = self.bg.copy()
            n = int(round(sc["count"] * ease_out(fr / 1.3)))
            big = f("display", 520, 900)
            y = int(H * .22)
            self.text_in(img, (M - 14, y), f"{n}", big, c["ink"], fr / .3, rise=40)
            d = ImageDraw.Draw(img)
            nx = M - 14 + d.textlength(f"{sc['count']}", font=big) + 10
            self.text_in(img, (nx, y + 70), "+", f("display", 220, 900), c["accent"], (fr - .9) / .3, rise=20)
            ly = y + 560
            for i, line in enumerate(sc["label"]):
                self.text_in(img, (M, ly + i * 120), line, f("display", 130, 900),
                             c["accent"] if i else c["ink"], (fr - .3 - i * .2) / .4)
            ly += 2 * 120 + 70
            self.bar(img, M, ly, W - 2 * M, 2, (fr - .6) / .6, c["line"])
            ly += 40
            for i, line in enumerate(sc["lines"]):
                self.text_in(img, (M, ly + i * 64), line, f("body", 32, 700),
                             c["ink"] if i < 3 else c["soft"], (fr - .8 - i * .16) / .4, rise=16)
            return img
        if k == "credits":
            img = self.bg.copy()
            y = int(H * .26)
            self.text_in(img, (M, y), sc["kicker"], f("body", 34, 800), c["accent"], fr / .35, rise=20)
            self.bar(img, M, y + 60, 140, 8, (fr - .1) / .4, c["accent"])
            ft = f("display", 92, 800)
            for i, line in enumerate(sc["lines"]):
                col = c["ink"] if i < 4 else c["soft"]
                self.text_in(img, (M, y + 110 + i * 132), line, ft, col, (fr - .2 - i * .2) / .4, rise=40)
                pp = (fr - .35 - i * .2) / .5
                self.bar(img, M, y + 110 + i * 132 + 112, W - 2 * M, 1, pp, c["line"])
            return img
        if k == "end":
            img = self.bg.copy()
            glow = Image.new("RGB", (W, H), (0, 0, 0))
            ImageDraw.Draw(glow).ellipse([W / 2 - 520, H * .46 - 420, W / 2 + 520, H * .46 + 420], fill=c["accent"])
            img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(220)), .22 * ease_out(fr / .8))
            size = 300
            lg = self.logo.resize((size, size), Image.LANCZOS)
            a = ease_out(fr / .5)
            lg.putalpha(lg.split()[3].point(lambda v: int(v * a)))
            img.paste(lg, (W // 2 - size // 2, int(H * .16)), lg)
            self.text_in(img, (W / 2, H * .37), sc["cta"], f("body", 40, 800), c["soft"], (fr - .2) / .4,
                         rise=20, anchor="mt")
            # url, sized to fit
            us = 190
            while ImageDraw.Draw(img).textlength(sc["url"], font=f("display", us, 900)) > W - 2 * M + 10:
                us -= 6
            self.text_in(img, (W / 2, H * .41), sc["url"], f("display", us, 900), c["ink"], (fr - .35) / .45,
                         anchor="mt")
            # button
            pb = ease_out((fr - .75) / .45)
            if pb > 0:
                d = ImageDraw.Draw(img)
                bw, bh = int(720 * (.9 + .1 * pb)), 128
                bx, by = W // 2 - bw // 2, int(H * .57)
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ld = ImageDraw.Draw(lay)
                ld.rounded_rectangle([bx, by, bx + bw, by + bh], radius=64, fill=c["accent"] + (int(255 * pb),))
                ld.text((W / 2, by + bh / 2), self.s.get("button", "FREE ESTIMATE"), font=f("display", 64, 900),
                        fill=(255, 255, 255, int(255 * pb)), anchor="mm")
                img.paste(lay, (0, 0), lay)
            self.text_in(img, (W / 2, H * .57 + 170), sc["alt"], f("body", 40, 700), c["ink"], (fr - 1.0) / .4,
                         rise=16, anchor="mt")
            self.text_in(img, (W / 2, H * .57 + 236), sc["foot"], f("body", 28, 500), c["mute"], (fr - 1.15) / .4,
                         rise=12, anchor="mt")
            lic = self.s.get("license", "NJ Master Plumber #36BI00464600  ·  HVAC #19HC00178300  ·  Fire #P01631")
            self.text_in(img, (W / 2, H - 230), lic, f("body", 22, 600), c["mute"], (fr - 1.3) / .4, rise=8,
                         anchor="mt")
            return img
        raise ValueError(k)

    def finish(self, img, gi, wipe):
        c = self.c
        img = Image.composite(img, self.black, self.vig.point(lambda v: 150 + int(v * 105 / 255)))
        img = Image.blend(img, Image.merge("RGB", [self.grain[gi % 4]] * 3), .045)
        if wipe is not None:  # brand wipe: -1..0 entering (cover), 0..1 leaving (reveal)
            d = ImageDraw.Draw(img)
            if wipe < 0:
                top = int(H * ease_io(-wipe))
                d.rectangle([0, top, W, H], fill=c["bg"])
                d.rectangle([0, top - 14, W, top], fill=c["accent"])
            else:
                bot = int(H * (1 - ease_io(wipe)))
                d.rectangle([0, 0, W, bot], fill=c["bg"])
                d.rectangle([0, bot, W, bot + 14], fill=c["accent"])
        return img


# ---------- score ----------
def score(total, cuts, out, sr=44100):
    """Synthesized cinematic bed: sub drone, filtered pulse, risers into each cut, impacts on each cut."""
    n = int(total * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(3)
    root = 55.0
    mix = np.zeros(n)
    # drone (root + fifth), slow swell
    sw = 0.55 + 0.45 * np.sin(2 * np.pi * t / 9.0) ** 2
    mix += 0.16 * sw * (np.sin(2 * np.pi * root * t) + 0.5 * np.sin(2 * np.pi * root * 1.5 * t)
                        + 0.25 * np.sin(2 * np.pi * root * 2 * t))
    # pulse at 100 bpm: soft kick + ticking hat
    beat = 60 / 100
    for k in range(int(total / beat) + 1):
        s = int(k * beat * sr)
        L = int(.35 * sr)
        if s >= n:
            break
        e = min(L, n - s)
        tt = np.arange(e) / sr
        mix[s:s + e] += 0.42 * np.sin(2 * np.pi * (48 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
        h = int((k * beat + beat / 2) * sr)
        hl = min(int(.05 * sr), n - h)
        if hl > 0:
            mix[h:h + hl] += 0.05 * rng.normal(0, 1, hl) * np.exp(-np.arange(hl) / sr * 90)
    # risers + impacts
    for c in cuts:
        rs, re_ = int(max(0, c - .55) * sr), int(c * sr)
        if re_ > rs:
            rt = np.linspace(0, 1, re_ - rs)
            mix[rs:re_] += 0.10 * rng.normal(0, 1, re_ - rs) * rt ** 2
        s = int(c * sr)
        L = min(int(1.4 * sr), n - s)
        if L > 0:
            tt = np.arange(L) / sr
            mix[s:s + L] += 0.55 * np.sin(2 * np.pi * (38 + 60 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 3.2)
            mix[s:s + L] += 0.12 * rng.normal(0, 1, L) * np.exp(-tt * 14)
    # fade in/out
    fi, fo = int(.4 * sr), int(1.6 * sr)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.85
    pcm = (mix * 32767).astype("<i2")
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
    return out


def scene_times(beats, audio_len, n_scenes, tail=1.8, lead=0.25):
    weights = [max(len(b.split()), 3) + 1.4 for b in beats[:n_scenes]]
    while len(weights) < n_scenes:
        weights.append(4)
    tot = sum(weights)
    durs = [audio_len * w / tot for w in weights]
    durs[0] += lead
    durs[-1] += tail
    return durs


def video(ad_id, beats, audio_path, audio_len, workdir, out_path):
    spec = ADS[ad_id]
    ad = Ad(spec)
    scenes = spec["scenes"]
    durs = scene_times(beats, audio_len, len(scenes))
    total = sum(durs)
    starts = np.cumsum([0] + durs[:-1])
    nframes = int(total * FPS)
    music = score(total, [float(s) for s in starts[1:]], os.path.join(workdir, "score.wav"))
    raw = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         os.path.join(workdir, "picture.mp4")], stdin=subprocess.PIPE)
    WIPE = 7  # frames each side of a cut
    for fi in range(nframes):
        tg = fi / FPS
        si = int(np.searchsorted(starts, tg, side="right") - 1)
        sc_t = (tg - starts[si]) / durs[si]
        img = ad.scene(scenes[si], sc_t, durs[si])
        if scenes[si]["type"] not in ("logo", "end"):
            ad.hud(img, si, len(scenes), tg / total)
        wipe = None
        f_in = (tg - starts[si]) * FPS
        f_left = (starts[si] + durs[si] - tg) * FPS
        if si > 0 and f_in < WIPE:
            wipe = f_in / WIPE
        elif si < len(scenes) - 1 and f_left < WIPE:
            wipe = -(1 - f_left / WIPE)
        if fi < 8:
            img = Image.blend(Image.new("RGB", (W, H)), img, fi / 8)
        img = ad.finish(img, fi, wipe)
        raw.stdin.write(img.tobytes())
    raw.stdin.close()
    raw.wait()
    pic = os.path.join(workdir, "picture.mp4")
    if audio_path:
        fc = ("[1:a]adelay=250|250,apad,volume=1.6,asplit=2[vo1][vo2];[2:a]volume=0.55[m];"
              "[m][vo1]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=350[md];"
              "[md][vo2]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", audio_path, "-i", music,
               "-filter_complex", fc, "-map", "0:v", "-map", "[a]"]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", music, "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", "-movflags", "+faststart",
            out_path]
    subprocess.run(cmd, check=True)
    return out_path


if __name__ == "__main__":  # preview without a voiceover: python engine/client_ad.py newark-premium out.mp4 [seconds]
    import sys
    import tempfile
    aid, out = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    beats = [x for x in (sys.argv[4:] or [])] or ["x " * 6] * len(ADS[aid]["scenes"])
    video(aid, beats, None, secs, tempfile.mkdtemp(), out)
    print(out)
