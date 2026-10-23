"""Product-drop flyer: real product cutouts (assets/products/<set>/) on the HSW365 dark-premium look.
Used by engine/flyer.py for FLYERS entries with "layout": "collection"."""
import os
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import flyer as F

ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD = (251, 191, 36)
EMBER = (239, 68, 68)


def _bg(w, h):
    img = Image.new("RGB", (w, h), F.BASE)
    glow = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(glow)
    d.ellipse([int(w * .05), int(h * .28), int(w * .95), int(h * .78)], fill=(120, 70, 10))
    d.ellipse([-int(w * .4), -int(h * .15), int(w * .6), int(h * .35)], fill=(80, 14, 18))
    d.ellipse([int(w * .5), int(h * .75), int(w * 1.4), int(h * 1.2)], fill=(70, 22, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(min(w, h) // 4))
    img = ImageChops.screen(img, ImageChops.multiply(glow, Image.new("RGB", (w, h), (150, 150, 150))))
    g = ImageDraw.Draw(img)
    for x in range(0, w, 60):
        g.line([(x, 0), (x, h)], fill=(17, 15, 20))
    for y in range(0, h, 60):
        g.line([(0, y), (w, y)], fill=(17, 15, 20))
    # bleach-splatter specks, the same texture as the tees
    import random
    rnd = random.Random(365)
    sp = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(sp)
    for _ in range(420):
        x, y = rnd.gauss(w * .5, w * .45), rnd.gauss(h * .5, h * .35)
        r = rnd.choice([1, 1, 1, 1, 2])
        sd.ellipse([x - r, y - r, x + r, y + r], fill=rnd.randint(30, 110))
    img = Image.composite(Image.new("RGB", (w, h), (230, 190, 120)), img, sp)
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    return Image.blend(img, noise, 0.035)


def _tee(img, path, cx, cy, height, angle=0, glow=GOLD):
    t = Image.open(path).convert("RGBA")
    t = t.resize((int(t.width * height / t.height), height), Image.LANCZOS)
    if angle:
        t = t.rotate(angle, resample=Image.BICUBIC, expand=True)
    a = t.getchannel("A")
    x, y = cx - t.width // 2, cy - t.height // 2
    # colored halo behind
    halo = Image.new("L", img.size, 0)
    halo.paste(a, (x, y))
    halo = halo.filter(ImageFilter.GaussianBlur(height // 9))
    img.paste(ImageChops.screen(img, Image.composite(Image.new("RGB", img.size, tuple(int(c * .55) for c in glow)),
                                                     Image.new("RGB", img.size), halo)))
    # contact shadow
    sh = Image.new("L", img.size, 0)
    sh.paste(a, (x + height // 30, y + height // 22))
    sh = sh.filter(ImageFilter.GaussianBlur(height // 28)).point(lambda v: int(v * .75))
    img.paste(Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, sh))
    img.paste(t, (x, y), t)


def draw(s, w, h):
    img = _bg(w, h)
    d = ImageDraw.Draw(img)
    k = w / 1080
    story = h / w > 1.6
    M = 72
    pdir = os.path.join(ROOT, "assets", "products", s["set"])

    mono = F.font("m", int(26 * k))
    y = int((120 if story else 64) * k)
    d.text((M, y), s.get("brand", "HSW365.CO"), font=mono, fill=GOLD)
    d.text((w - M - d.textlength(s["tag"], font=mono), y), s["tag"], font=mono, fill=F.MUTED)
    d.rectangle([M, y + int(48 * k), M + int(110 * k), y + int(54 * k)], fill=EMBER)

    y += int((100 if story else 82) * k)
    d.text((M, y), s["kicker"], font=F.font("m", int(23 * k)), fill=F.SOFT)
    y += int(44 * k)
    hsz = int((170 if story else 118) * k)
    hf = F.font("x", hsz)
    F._grad_text(img, (M - 4, y + int(hsz * .9)), s["head"][1], hf, EMBER, GOLD)
    d = ImageDraw.Draw(img)
    d.text((M - 4, y), s["head"][0], font=hf, fill=F.WHITE)
    y += int(hsz * .9) * 2 + int((36 if story else 26) * k)

    sf = F.font("i", int((31 if story else 28) * k))
    for line in F._wrap(d, s["sub"], sf, w - 2 * M - int(40 * k)):
        d.text((M, y), line, font=sf, fill=F.SOFT)
        y += int((44 if story else 40) * k)

    # hero: three real tees, fanned
    hero_top = y + int((30 if story else 10) * k)
    hero_h = int((580 if story else 400) * k)
    cy = hero_top + hero_h // 2
    big, side = int(hero_h * .86), int(hero_h * .66)
    left, center, right = s["hero"]
    _tee(img, os.path.join(pdir, f"tee{left}.png"), int(w * .24), cy + int(hero_h * .06), side, 9, GOLD)
    _tee(img, os.path.join(pdir, f"tee{right}.png"), int(w * .76), cy + int(hero_h * .06), side, -9, (110, 90, 255))
    _tee(img, os.path.join(pdir, f"tee{center}.png"), w // 2, cy, big, 0, EMBER)
    d = ImageDraw.Draw(img)
    # "1 OF 1" seal on the center piece
    sr = int(62 * k)
    sx, sy = w // 2 + int(big * .36), hero_top + int(hero_h * .10)
    d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=EMBER, outline=GOLD, width=max(2, int(3 * k)))
    for txt, dy, fs in (("1 OF 1", -int(20 * k), 30), ("SIGNED", int(14 * k), 18)):
        f = F.font("x" if fs == 30 else "m", int(fs * k))
        d.text((sx - d.textlength(txt, font=f) / 2, sy + dy - int(fs * k * .55)), txt, font=f, fill=F.WHITE)
    y = hero_top + hero_h + int((34 if story else 16) * k)

    # the drop list: every piece by number and name
    d.text((M, y), s["list_title"], font=F.font("m", int(21 * k)), fill=GOLD)
    d.line([(M + int(d.textlength(s["list_title"], font=F.font("m", int(21 * k))) + 24 * k), y + int(13 * k)),
            (w - M, y + int(13 * k))], fill=F.LINE, width=2)
    y += int(40 * k)
    gap = int(14 * k)
    cols = 2
    cw = (w - 2 * M - gap) // cols
    rh = int((62 if story else 46) * k)
    nf, tf = F.font("m", int((20 if story else 17) * k)), F.font("b", int((36 if story else 28) * k))
    for i, (num, name) in enumerate(s["pieces"]):
        cx = M + (i % cols) * (cw + gap)
        ry = y + (i // cols) * (rh + gap // 2)
        F._alpha_box(img, [cx, ry, cx + cw, ry + rh], (20, 16, 22), F.LINE, radius=int(12 * k), alpha=215)
        d = ImageDraw.Draw(img)
        d.rectangle([cx, ry + int(14 * k), cx + int(5 * k), ry + rh - int(14 * k)], fill=EMBER if i % 2 == 0 else GOLD)
        d.text((cx + int(22 * k), ry + (rh - nf.size) // 2 - int(3 * k)), "#" + num, font=nf, fill=F.MUTED)
        nx = cx + int(22 * k) + d.textlength("#000  ", font=nf)
        ff = tf
        while d.textlength(name, font=ff) > cx + cw - nx - int(16 * k) and ff.size > 14:
            ff = F.font("b", ff.size - 1)
        d.text((nx, ry + (rh - ff.size) // 2 - int(4 * k)), name, font=ff, fill=F.WHITE)
    y += ((len(s["pieces"]) + 1) // cols) * (rh + gap // 2) + int((34 if story else 18) * k)

    # price + CTA
    pf = F.font("x", int((96 if story else 72) * k))
    d.text((M, y - int(6 * k)), s["price"], font=pf, fill=F.WHITE)
    px = M + d.textlength(s["price"], font=pf) + int(16 * k)
    d.text((px, y + int((22 if story else 14) * k)), s["price_note"][0], font=F.font("m", int(19 * k)), fill=GOLD)
    d.text((px, y + int((50 if story else 38) * k)), s["price_note"][1], font=F.font("m", int(19 * k)), fill=F.SOFT)
    cf = F.font("x", int((64 if story else 54) * k))
    bw = d.textlength(s["cta"], font=cf) + int(80 * k)
    bh = int((100 if story else 82) * k)
    bx = w - M - bw
    glow = Image.new("RGB", img.size)
    ImageDraw.Draw(glow).rounded_rectangle([bx, y, bx + bw, y + bh], radius=int(16 * k), fill=EMBER)
    img.paste(ImageChops.screen(img, ImageChops.multiply(glow.filter(ImageFilter.GaussianBlur(34)),
                                                         Image.new("RGB", img.size, (120, 120, 120)))))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=int(16 * k), fill=EMBER)
    d.text((bx + int(40 * k), y + (bh - cf.size) // 2 - int(6 * k)), s["cta"], font=cf, fill=F.WHITE)
    fy = h - int((90 if story else 52) * k)
    d.line([(M, fy), (w - M, fy)], fill=F.LINE, width=2)
    ff = F.font("m", int(20 * k))
    d.text((M, fy + int(16 * k)), s["url"], font=F.font("m", int(24 * k)), fill=GOLD)
    d.text((M + d.textlength(s["url"] + "  ", font=F.font("m", int(24 * k))), fy + int(19 * k)), s["alt"], font=ff,
           fill=F.SOFT)
    t = "VETERAN OWNED"
    d.text((w - M - d.textlength(t, font=ff), fy + int(18 * k)), t, font=ff, fill=F.MUTED)
    return img
