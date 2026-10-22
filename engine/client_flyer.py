"""Client service flyers: a trade-business flyer in the client's own brand (colors, fonts, logo, job photos),
not HSW365's. Used by engine/flyer.py for any FLYERS entry with "layout": "service".

Spec keys:
  brand      folder under assets/clients/ holding logo.webp, the fonts and photos
  colors     {"bg", "bg2", "accent", "accent2", "ink", "soft", "mute", "line"} as hex
  fonts      {"display": file, "body": file}  (variable fonts; weight set per use)
  photo      photo file in the brand folder used as the hero band
  kicker     small line above the headline
  head       [line 1 (white), line 2 (accent)]
  sub        one or two sentences
  tiles      [(title, detail), ...] four is ideal
  proof      short trust lines shown as a strip (licenses, years)
  cta        button text
  url        the website, big
  alt        second contact line (phone)
  foot       left footer text
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.join(os.path.dirname(__file__), "..")
CLIENTS = os.path.join(ROOT, "assets", "clients")


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class _Fonts:
    def __init__(self, folder, files):
        self.folder, self.files, self.cache = folder, files, {}

    def __call__(self, kind, size, weight):
        key = (kind, size, weight)
        if key not in self.cache:
            f = ImageFont.truetype(os.path.join(self.folder, self.files[kind]), size)
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
            self.cache[key] = f
        return self.cache[key]


def _wrap(d, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(d, text, F, kind, size, weight, max_w, floor=12):
    f = F(kind, size, weight)
    while d.textlength(text, font=f) > max_w and size > floor:
        size -= 2
        f = F(kind, size, weight)
    return f


def _box(img, box, fill, alpha, outline=None, radius=0, width=2):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill + (alpha,),
                                            outline=(outline + (255,)) if outline else None, width=width)
    img.alpha_composite(layer)


def draw(s, w, h):
    folder = os.path.join(CLIENTS, s["brand"])
    c = {k: _rgb(v) for k, v in s["colors"].items()}
    F = _Fonts(folder, s["fonts"])
    k = w / 1080
    story = h / w > 1.6
    M = int(68 * k)

    img = Image.new("RGBA", (w, h), c["bg"] + (255,))
    # deep vertical gradient
    grad = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGBA", (w, h), c["bg2"] + (255,)), img, grad)

    # hero photo band with a blueprint-dark wash, fading into the page
    band_h = int((760 if story else 560) * k)
    photo = Image.open(os.path.join(folder, s["photo"])).convert("RGB")
    photo = ImageOps.fit(photo, (w, band_h), Image.LANCZOS, centering=(0.5, 0.45))
    photo = ImageOps.colorize(ImageOps.grayscale(photo), c["bg"], (225, 232, 242)).convert("RGBA")
    photo = Image.blend(photo, Image.new("RGBA", photo.size, c["bg"] + (255,)), 0.42)
    fade = Image.linear_gradient("L").resize((w, band_h))  # 0 top -> 255 bottom
    fade = fade.point(lambda v: 255 - int(max(0, v - 70) * 255 / 185))
    img.paste(photo, (0, 0), fade)
    d = ImageDraw.Draw(img)

    # top bar: logo + brand + tag
    logo_sz = int(132 * k)
    logo = Image.open(os.path.join(folder, "logo.webp")).convert("RGB").resize((logo_sz, logo_sz), Image.LANCZOS)
    mask = Image.new("L", (logo_sz, logo_sz), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, logo_sz, logo_sz], radius=int(18 * k), fill=255)
    ty = int((96 if story else 56) * k)
    _box(img, [M - 6, ty - 6, M + logo_sz + 6, ty + logo_sz + 6], (255, 255, 255), 40, radius=int(22 * k))
    img.paste(logo, (M, ty), mask)
    d = ImageDraw.Draw(img)
    nx = M + logo_sz + int(28 * k)
    d.text((nx, ty + int(14 * k)), s["name"][0], font=F("display", int(58 * k), 800), fill=c["ink"])
    d.text((nx, ty + int(78 * k)), s["name"][1], font=F("body", int(24 * k), 600), fill=c["soft"])

    # kicker + headline, sitting on the faded photo
    y = band_h - int((300 if story else 250) * k)
    kf = F("body", int(25 * k), 700)
    d.rectangle([M, y + int(6 * k), M + int(8 * k), y + int(30 * k)], fill=c["accent"])
    d.text((M + int(22 * k), y), s["kicker"].upper(), font=kf, fill=c["soft"])
    y += int(48 * k)
    hsize = int((150 if story else 124) * k)
    h1 = _fit(d, s["head"][0], F, "display", hsize, 900, w - 2 * M)
    h2 = _fit(d, s["head"][1], F, "display", hsize, 900, w - 2 * M)
    d.text((M - 3, y), s["head"][0], font=h1, fill=c["ink"])
    y += int(h1.size * 0.96)
    d.text((M - 3, y), s["head"][1], font=h2, fill=c["accent"])
    y += int(h2.size * 1.08) + int(14 * k)

    sf = F("body", int((33 if story else 29) * k), 400)
    for line in _wrap(d, s["sub"], sf, w - 2 * M - int(40 * k)):
        d.text((M, y), line, font=sf, fill=c["soft"])
        y += int(sf.size * 1.42)

    # service tiles
    y += int((44 if story else 24) * k)
    gap = int(16 * k)
    cols = 2
    cw = (w - 2 * M - gap) // cols
    ch = int((150 if story else 96) * k)
    for i, (title, detail) in enumerate(s["tiles"]):
        cx = M + (i % cols) * (cw + gap)
        cy = y + (i // cols) * (ch + gap)
        _box(img, [cx, cy, cx + cw, cy + ch], c["panel"], 235, outline=c["line"], radius=int(12 * k))
        d = ImageDraw.Draw(img)
        d.rectangle([cx, cy, cx + int(6 * k), cy + ch], fill=c["accent"] if i % 3 == 0 else c["accent2"])
        tf = _fit(d, title.upper(), F, "display", int(44 * k), 800, cw - int(48 * k))
        d.text((cx + int(28 * k), cy + int((20 if story else 14) * k)), title.upper(), font=tf, fill=c["ink"])
        if story:
            df = _fit(d, detail, F, "body", int(23 * k), 400, cw - int(48 * k))
            d.text((cx + int(28 * k), cy + int(82 * k)), detail, font=df, fill=c["soft"])
    rows = (len(s["tiles"]) + cols - 1) // cols
    y += rows * ch + (rows - 1) * gap + int((40 if story else 24) * k)

    # proof strip
    pf = F("body", int((21 if story else 19) * k), 600)
    proof = "   |   ".join(s["proof"])
    pf = _fit(d, proof, F, "body", pf.size, 600, w - 2 * M)
    d.line([(M, y), (w - M, y)], fill=c["line"], width=2)
    d.text((M, y + int(16 * k)), proof, font=pf, fill=c["mute"])
    y += int(16 * k) + pf.size + int(16 * k)
    d.line([(M, y), (w - M, y)], fill=c["line"], width=2)
    y += int((52 if story else 30) * k)

    # CTA: button + website + alt contact, anchored just above the footer
    fy = h - int((92 if story else 58) * k)
    block = int((104 + 34 + 100 + 44) * k) if story else int(104 * k)
    y = max(y, fy - block - int((70 if story else 52) * k))
    bf = F("display", int(64 * k), 900)
    bw = int(d.textlength(s["cta"], font=bf) + 84 * k)
    bh = int(104 * k)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([M, y, M + bw, y + bh], radius=int(10 * k), fill=c["accent"] + (150,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(int(26 * k))))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([M, y, M + bw, y + bh], radius=int(10 * k), fill=c["accent"])
    d.text((M + int(42 * k), y + int(16 * k)), s["cta"], font=bf, fill=(255, 255, 255))
    if story:
        y += bh + int(34 * k)
        uf = _fit(d, s["url"], F, "display", int(96 * k), 900, w - 2 * M)
        d.text((M, y), s["url"], font=uf, fill=c["ink"])
        y += int(uf.size * 1.05)
        d.text((M, y), s["alt"], font=F("body", int(30 * k), 600), fill=c["soft"])
    else:
        ux = M + bw + int(30 * k)
        uf = _fit(d, s["url"], F, "display", int(62 * k), 900, w - M - ux)
        d.text((ux, y - int(2 * k)), s["url"], font=uf, fill=c["ink"])
        af = _fit(d, s["alt"], F, "body", int(22 * k), 600, w - M - ux)
        d.text((ux, y + int(68 * k)), s["alt"], font=af, fill=c["soft"])

    # footer
    d.line([(M, fy), (w - M, fy)], fill=c["line"], width=2)
    ff = F("body", int(19 * k), 600)
    d.text((M, fy + int(18 * k)), s["foot"].upper(), font=ff, fill=c["mute"])
    t = s.get("foot_right", "").upper()
    if t:
        d.text((w - M - d.textlength(t, font=ff), fy + int(18 * k)), t, font=ff, fill=c["mute"])
    return img.convert("RGB")
