"""Instagram carousel slides: the same script as a video, one beat per swipeable slide (1080x1350 JPEG)."""
import os

from PIL import Image, ImageDraw, ImageFilter

import render

W, H = 1080, 1350


def _background(i, n):
    img = Image.new("RGB", (W, H), render.BASE)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    t = i / max(n - 1, 1)
    cx1, cy1 = int(W * (0.15 + 0.5 * t)), int(H * 0.25)
    cx2, cy2 = int(W * (0.85 - 0.4 * t)), int(H * 0.78)
    d.ellipse([cx1 - 480, cy1 - 480, cx1 + 480, cy1 + 480], fill=(14, 70, 84))
    d.ellipse([cx2 - 520, cy2 - 520, cx2 + 520, cy2 + 520], fill=(62, 26, 92))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(200)), 0.55)
    g = ImageDraw.Draw(img)
    for x in range(0, W, 90):
        g.line([(x, 0), (x, H)], fill=(18, 18, 26), width=1)
    for y in range(0, H, 90):
        g.line([(0, y), (W, y)], fill=(18, 18, 26), width=1)
    return img


def slide(text, emphasis, i, n, product, out, cta=None, brand="HSW365 MEDIA", handle="HSW365MEDIA"):
    img = _background(i, n)
    d = ImageDraw.Draw(img)
    mono = render._font("SpaceMono-Bold.ttf", 28)
    d.text((70, 80), brand.upper(), font=mono, fill=render.CYAN)
    count = f"{i + 1:02d} / {n:02d}"
    d.text((W - 70 - d.textlength(count, font=mono), 80), count, font=mono, fill=render.MUTED)
    d.rectangle([70, 132, 190, 138], fill=render.VIOLET)

    last = i == n - 1
    words = text.upper().split()
    size = 150 if len(words) <= 5 else 128 if len(words) <= 7 else 112
    while True:
        font = render._font("BarlowCondensed-ExtraBold.ttf", size)
        lines = render._wrap(words, font, d, W - 160)
        widest = max(d.textlength(w, font=font) for w in words)
        if (len(lines) <= 5 and widest <= W - 160) or size <= 60:
            break
        size -= 10
    lh = int(size * 1.02)
    extra = 230 if last else 0
    y = (H - lh * len(lines) - extra) // 2
    emph = (emphasis or "").upper().strip(".,!?")
    kw = product["keyword"].upper()
    for line in lines:
        x = 80
        for w in line:
            bare = w.strip(".,!?'\"")
            color = render.WHITE
            if bare == kw or (last and kw in bare):
                color = render.YELLOW
            elif emph and bare == emph:
                color = render.CYAN
            d.text((x, y), w, font=font, fill=color)
            x += d.textlength(w + " ", font=font)
        y += lh

    if last:
        pill = render._font("BarlowCondensed-ExtraBold.ttf", 70)
        label, sub = cta or (f"COMMENT \"{kw}\"", f"OR DM IT TO @{handle.upper()}")
        while d.textlength(label, font=pill) > W - 240 and pill.size > 40:
            pill = render._font("BarlowCondensed-ExtraBold.ttf", pill.size - 4)
        tw = d.textlength(label, font=pill)
        by = y + 50
        d.rounded_rectangle([80, by, 80 + tw + 80, by + 112], radius=18, fill=render.RED)
        d.text((120, by + (112 - pill.size) // 2 - 8), label, font=pill, fill=render.WHITE)
        d.text((80, by + 140), sub, font=mono, fill=render.MUTED)
    else:
        d.text((W - 70 - d.textlength("SWIPE >", font=mono), H - 110), "SWIPE >", font=mono, fill=render.MUTED)

    tag = f"// {product['name']}"
    d.text((70, H - 110), tag, font=mono, fill=render.MUTED)
    img.save(out, "JPEG", quality=92)  # Instagram only accepts JPEG for carousel images


def render_slides(beats, emphasis, product, outdir, slug, cta=None, brand="HSW365 MEDIA", handle="HSW365MEDIA"):
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for i, (b, e) in enumerate(zip(beats, emphasis)):
        p = os.path.join(outdir, f"{slug}-{i + 1:02d}.jpg")
        slide(b, e, i, len(beats), product, p, cta, brand, handle)
        paths.append(p)
    return paths
