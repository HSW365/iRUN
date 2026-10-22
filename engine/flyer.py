"""Flyers: HSW365 dark-premium promo flyers as PNG, plus the flyer turned into a short voiced video so iRun can
post it to TikTok, Instagram Reels and YouTube Shorts through the normal publish path.

Queue item that posts a flyer (see engine/content_queue.py):
{
  "account": "hsw365media", "product": "operator", "platform": "tiktok",
  "flyer": "irun-services",                 # id in FLYERS below
  "beats": ["voiceover line", ...],         # 3-9 lines, spoken over the flyer
  "caption": "...", "hashtags": [...]
}

Build the PNGs by hand:  python engine/flyer.py irun-services  -> assets/flyers/irun-services-{story,feed}.png
"""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import client_flyer  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
F = os.path.join(ROOT, "assets", "hsw", "fonts")
OUT = os.path.join(ROOT, "assets", "flyers")

BASE = (10, 10, 15)
PANEL = (17, 17, 26)
LINE = (34, 34, 48)
CYAN = (34, 211, 238)
VIOLET = (168, 85, 247)
RED = (239, 68, 68)
YELLOW = (251, 191, 36)
WHITE = (244, 244, 248)
SOFT = (176, 176, 196)
MUTED = (112, 112, 134)


def font(kind, size):
    files = {"x": "barlow-condensed-latin-900-normal.woff2", "b": "barlow-condensed-latin-800-normal.woff2",
             "s": "barlow-condensed-latin-600-normal.woff2", "m": "space-mono-latin-700-normal.woff2",
             "mr": "space-mono-latin-400-normal.woff2", "i": "inter-latin-wght-normal.woff2"}
    f = ImageFont.truetype(os.path.join(F, files[kind]), size)
    if kind == "i":
        try:
            f.set_variation_by_axes([500])
        except Exception:
            pass
    return f


FLYERS = {
    "irun-services": {
        "tag": "// iRUN OPERATOR",
        "kicker": "AI MARKETING TEAM  /  24-7 AUTOPILOT",
        "head": ["YOUR BUSINESS.", "ON AUTOPILOT."],
        "sub": "iRun creates your content, posts it everywhere and turns attention into customers. No agency. No burnout.",
        "services": [
            ("01", "DAILY VIDEOS", "Auto-posted to TikTok, Reels, Shorts"),
            ("02", "FACELESS STORIES", "Cinematic AI videos, voiced + captioned"),
            ("03", "AI WEBSITE", "A new site built from one link"),
            ("04", "DM LEAD CAPTURE", "Comments and DMs turned into leads"),
            ("05", "COLD OUTREACH", "Emails your prospects every day"),
            ("06", "SEO ON EVERY POST", "Top keywords and hashtags, built in"),
            ("07", "NIGHTLY AI CEO", "Reviews results, plans tomorrow"),
            ("08", "LIVE DASHBOARD", "Every post, lead and credit, live"),
        ],
        "plans": [("STARTER", "15", "15 credits / mo", False), ("PRO", "35", "30 credits / mo", True),
                  ("ELITE", "60", "60 credits / mo", False)],
        "cta": "START TODAY",
        "url": "HSW365.GITHUB.IO/IRUN/START",
        "foot": "COMMENT \"RUN\" OR DM @HSW365MEDIA",
    }
}


def _bg(w, h):
    img = Image.new("RGB", (w, h), BASE)
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse([-int(w * .35), -int(h * .12), int(w * .75), int(h * .42)], fill=(12, 78, 96))
    d.ellipse([int(w * .35), int(h * .30), int(w * 1.4), int(h * .95)], fill=(70, 26, 110))
    d.ellipse([-int(w * .3), int(h * .78), int(w * .5), int(h * 1.25)], fill=(60, 14, 20))
    glow = glow.filter(ImageFilter.GaussianBlur(min(w, h) // 4))
    img = Image.blend(img, glow, 0.5)
    g = ImageDraw.Draw(img)
    for x in range(0, w, 60):
        g.line([(x, 0), (x, h)], fill=(17, 17, 25))
    for y in range(0, h, 60):
        g.line([(0, y), (w, y)], fill=(17, 17, 25))
    # film grain for a printed, non-flat finish
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    return Image.blend(img, noise, 0.035)


def _grad_text(img, xy, text, fnt, c1, c2):
    """Text filled with a left-to-right gradient, with a soft colored glow behind it."""
    from PIL import ImageChops
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = d.textbbox(xy, text, font=fnt)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255)
    grad = Image.new("RGB", (x1 - x0, 1))
    for i in range(x1 - x0):
        t = i / max(x1 - x0 - 1, 1)
        grad.putpixel((i, 0), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    layer = Image.new("RGB", img.size)
    layer.paste(grad.resize((x1 - x0, y1 - y0)), (x0, y0))
    glow = Image.composite(layer, Image.new("RGB", img.size), mask).filter(ImageFilter.GaussianBlur(34))
    img.paste(ImageChops.screen(img, ImageChops.multiply(glow, Image.new("RGB", img.size, (150, 150, 150)))))
    img.paste(layer, (0, 0), mask)


def _wrap(d, text, fnt, max_w):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and d.textlength(t, font=fnt) > max_w:
            out.append(cur)
            cur = w
        else:
            cur = t
    return out + ([cur] if cur else [])


def _alpha_box(img, box, fill, outline=None, radius=18, alpha=210, width=2):
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(over).rounded_rectangle(box, radius=radius, fill=fill + (alpha,),
                                          outline=(outline + (255,)) if outline else None, width=width)
    img.paste(Image.alpha_composite(img.convert("RGBA"), over).convert("RGB"))

NEWARK = {
    "layout": "service", "brand": "newark",
    "colors": {"bg": "#06182b", "bg2": "#0b2a4a", "panel": "#0d2340", "accent": "#c4161c", "accent2": "#1c5fb8",
               "ink": "#ffffff", "soft": "#c9d4e2", "mute": "#8797ab", "line": "#1f3d61"},
    "fonts": {"display": "big-shoulders.woff2", "body": "libre-franklin.woff2"},
    "name": ["NEW ARK", "PLUMBING, HEATING & AIR CONDITIONING"],
    "tiles": [("Plumbing", "Kitchens, baths, water heaters, drains, sewers"),
              ("Heating & AC", "Furnaces, boilers, ducts and equipment"),
              ("Geothermal", "Heating and cooling from the earth"),
              ("Fire Protection", "Sprinklers designed, installed, inspected")],
    "proof": ["NJ MASTER PLUMBER #36BI00464600", "HVAC #19HC00178300", "FIRE SPRINKLER #P01631"],
    "cta": "FREE ESTIMATE",
    "url": "ARK-HVAC.COM",
    "alt": "Message us 24/7 or call 908-454-4043",
    "foot": "412 Firth St, Phillipsburg, NJ",
    "foot_right": "Licensed and insured",
}
FLYERS.update({
    "newark-estimate": {**NEWARK, "photo": "hero.webp", "kicker": "Phillipsburg, NJ  /  nearly 40 years",
                        "head": ["FREE ESTIMATES.", "PRICED BY THE OWNER."],
                        "sub": "Plumbing, heating, air conditioning, geothermal and fire protection for homes and businesses. On time. On budget. On spec."},
    "newark-heat": {**NEWARK, "photo": "hvac.webp", "kicker": "Heating season is here",
                    "head": ["NO HEAT?", "WE REPLY IN MINUTES."],
                    "sub": "Furnaces, boilers and full HVAC systems repaired, replaced and installed. Message us any time, day or night, and get a free estimate."},
    "newark-trades": {**NEWARK, "photo": "plumbing.webp", "kicker": "Warren and Hunterdon County, NJ",
                      "head": ["FOUR TRADES.", "ONE CONTRACTOR."],
                      "sub": "Commercial and residential plumbing, HVAC, geothermal and fire protection from one licensed New Jersey contractor."},
    "newark-fire": {**NEWARK, "photo": "fire.webp", "kicker": "Commercial fire protection",
                    "head": ["FIRE SPRINKLERS.", "DONE TO CODE."],
                    "sub": "Sprinkler systems designed, installed and inspected by a licensed New Jersey fire sprinkler contractor."},
})


def draw(fid, w, h):
    s = FLYERS[fid]
    if s.get("layout") == "service":
        return client_flyer.draw(s, w, h)
    img = _bg(w, h)
    d = ImageDraw.Draw(img)
    M = 72
    k = w / 1080
    story = h / w > 1.6

    mono = font("m", int(26 * k))
    y = int((120 if story else 70) * k)
    d.text((M, y), "HSW365 MEDIA", font=mono, fill=CYAN)
    d.text((w - M - d.textlength(s["tag"], font=mono), y), s["tag"], font=mono, fill=MUTED)
    d.rectangle([M, y + int(48 * k), M + int(110 * k), y + int(54 * k)], fill=VIOLET)

    y += int((110 if story else 90) * k)
    d.text((M, y), s["kicker"], font=font("m", int(24 * k)), fill=SOFT)
    y += int(46 * k)
    hsz = int((156 if story else 112) * k)
    hf = font("x", hsz)
    _grad_text(img, (M - 4, y + int(hsz * .92)), s["head"][1], hf, CYAN, VIOLET)
    d = ImageDraw.Draw(img)
    d.text((M - 4, y), s["head"][0], font=hf, fill=WHITE)
    y += int(hsz * .92) * 2 + int((44 if story else 40) * k)

    sf = font("i", int(32 * k))
    for line in _wrap(d, s["sub"], sf, w - 2 * M - int(80 * k)):
        d.text((M, y), line, font=sf, fill=SOFT)
        y += int(46 * k)

    # services grid
    y += int((44 if story else 22) * k)
    d.text((M, y), "WHAT iRUN DOES FOR YOU", font=font("m", int(22 * k)), fill=CYAN)
    d.line([(M + int(390 * k), y + int(14 * k)), (w - M, y + int(14 * k))], fill=LINE, width=2)
    y += int(44 * k)
    gap = int((18 if story else 14) * k)
    cw = (w - 2 * M - gap) // 2
    ch = int((124 if story else 70) * k)
    nf, tf, df = font("m", int(22 * k)), font("b", int(40 * k)), font("i", int(22 * k))
    for i, (num, title, desc) in enumerate(s["services"]):
        cx = M + (i % 2) * (cw + gap)
        cy = y + (i // 2) * (ch + gap)
        _alpha_box(img, [cx, cy, cx + cw, cy + ch], PANEL, LINE, radius=int(16 * k), alpha=205)
        d = ImageDraw.Draw(img)
        d.rectangle([cx, cy + int(22 * k), cx + int(5 * k), cy + ch - int(22 * k)], fill=CYAN if i % 3 else VIOLET)
        d.text((cx + int(26 * k), cy + int(18 * k)), num, font=nf, fill=MUTED)
        d.text((cx + int(26 * k) + d.textlength(num + "  ", font=nf), cy + int(10 * k)), title, font=tf, fill=WHITE)
        dff = df
        while d.textlength(desc, font=dff) > cw - int(52 * k) and dff.size > 14:
            dff = font("i", dff.size - 1)
        if story:
            d.text((cx + int(26 * k), cy + int(70 * k)), desc, font=dff, fill=SOFT)
    y += 4 * ch + 3 * gap + int((58 if story else 34) * k)

    # plans
    pw = (w - 2 * M - 2 * gap) // 3
    ph = int((206 if story else 132) * k)
    for i, (name, price, cred, hot) in enumerate(s["plans"]):
        px = M + i * (pw + gap)
        _alpha_box(img, [px, y, px + pw, y + ph], (24, 16, 40) if hot else PANEL, VIOLET if hot else LINE,
                   radius=int(18 * k), alpha=230, width=3 if hot else 2)
        d = ImageDraw.Draw(img)
        if hot:
            badge = "MOST POPULAR"
            bf = font("m", int(18 * k))
            bw = d.textlength(badge, font=bf) + int(28 * k)
            d.rounded_rectangle([px + (pw - bw) // 2, y - int(17 * k), px + (pw + bw) // 2, y + int(17 * k)],
                                radius=int(17 * k), fill=VIOLET)
            d.text((px + (pw - bw) // 2 + int(14 * k), y - int(12 * k)), badge, font=bf, fill=WHITE)
        nm = name if story else f"{name}  /  {cred.split()[0]} CR"
        d.text((px + int(26 * k), y + int((28 if story else 22) * k)), nm, font=font("m", int((22 if story else 18) * k)),
               fill=CYAN if hot else SOFT)
        pf = font("x", int((88 if story else 58) * k))
        d.text((px + int(22 * k), y + int((54 if story else 46) * k)), "$" + price, font=pf, fill=WHITE)
        tw = d.textlength("$" + price, font=pf)
        d.text((px + int(30 * k) + tw, y + int((100 if story else 74) * k)), "/mo", font=font("s", int(32 * k)), fill=MUTED)
        if story:
            d.text((px + int(26 * k), y + ph - int(48 * k)), cred, font=font("i", int(21 * k)), fill=SOFT)
    y += ph + int((56 if story else 34) * k)

    # CTA
    cf = font("x", int(70 * k))
    cw2 = d.textlength(s["cta"], font=cf) + int(90 * k)
    chh = int(108 * k)
    glow = Image.new("RGB", img.size)
    ImageDraw.Draw(glow).rounded_rectangle([M, y, M + cw2, y + chh], radius=int(18 * k), fill=RED)
    from PIL import ImageChops
    img.paste(ImageChops.screen(img, ImageChops.multiply(glow.filter(ImageFilter.GaussianBlur(34)),
                                                         Image.new("RGB", img.size, (120, 120, 120)))))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([M, y, M + cw2, y + chh], radius=int(18 * k), fill=RED)
    d.text((M + int(45 * k), y + int(12 * k)), s["cta"], font=cf, fill=WHITE)
    ux = M + cw2 + int(34 * k)
    d.text((ux, y + int(14 * k)), "SIGN UP AT", font=font("m", int(20 * k)), fill=MUTED)
    uf = font("m", int(26 * k))
    url = s["url"]
    while d.textlength(url, font=uf) > w - M - ux and uf.size > 14:
        uf = font("m", uf.size - 1)
    d.text((ux, y + int(48 * k)), url, font=uf, fill=YELLOW)
    d.text((ux, y + int(86 * k)), s["foot"], font=font("m", int(17 * k)), fill=SOFT)

    # footer rule
    fy = h - int((100 if story else 60) * k)
    d.line([(M, fy), (w - M, fy)], fill=LINE, width=2)
    ff = font("m", int(20 * k))
    d.text((M, fy + int(18 * k)), "TURN NEGATIVE INTO POSITIVE", font=ff, fill=MUTED)
    t = "BUILT BY HSW365 MEDIA LLC"
    d.text((w - M - d.textlength(t, font=ff), fy + int(18 * k)), t, font=ff, fill=MUTED)
    return img


def build(fid, outdir=OUT):
    os.makedirs(outdir, exist_ok=True)
    paths = {}
    for kind, (w, h) in {"story": (1080, 1920), "feed": (1080, 1350)}.items():
        p = os.path.join(outdir, f"{fid}-{kind}.png")
        draw(fid, w, h).save(p, "PNG", optimize=True)
        paths[kind] = p
    return paths


def video(fid, audio_path, audio_len, workdir, out_path, tail=1.5):
    """The 9:16 flyer as a voiced video with a slow push-in, H.264 + AAC for TikTok / Reels / Shorts."""
    png = os.path.join(workdir, f"{fid}-story.png")
    draw(fid, 1080, 1920).save(png, "PNG")
    dur = max(audio_len + tail, 3.0)
    zoom = "zoompan=z='min(1+0.0001*on,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-t", f"{dur:.2f}", "-i", png,
         "-i", audio_path,
         "-filter_complex", f"[0:v]scale=1242:-1,{zoom},format=yuv420p[v];[1:a]apad=pad_dur={tail}[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", out_path],
        check=True,
    )
    return out_path


if __name__ == "__main__":
    for p in build(sys.argv[1] if len(sys.argv) > 1 else "irun-services").values():
        print(p)
