"""HSW365 Ad Studio micro-drama: "14 Views" - 30s, 1080x1920, 30fps.
A clothing-line owner's drop flops at 1 AM; a friend shows her the micro-drama ads
HSW365 made (New Ark, Friendy, LED mask); how they're made; price; QR to book."""
import io, math, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1080, 1920, 30, 30.0
N = int(FPS * DUR)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("IRUN", "/home/claude/irun")
ID = "/usr/share/fonts/opentype/inter/"
BC = os.path.join(REPO, "assets/fonts/BarlowCondensed-ExtraBold.ttf")
SM = os.path.join(REPO, "assets/fonts/SpaceMono-Bold.ttf")
def I(n, s): return ImageFont.truetype(ID + n, s)
def B(s): return ImageFont.truetype(BC, s)
def M(s): return ImageFont.truetype(SM, s)

RED = (239, 68, 68); CYAN = (34, 211, 238); GOLD = (251, 191, 36); WHITE = (244, 244, 247)
MUT = (143, 143, 159); INK = (10, 10, 15); CARD = (20, 20, 29); LINE = (44, 44, 56)
URL = "https://hsw365.github.io/iRUN/adstudio.html"

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def win(t, a, b, fi=0.35, fo=0.35):
    if t < a or t > b: return 0.0
    return min(ease((t - a) / fi) if fi else 1, ease((b - t) / fo) if fo else 1)

# ---------- backgrounds ----------
def vgrad(top, bot):
    y = np.linspace(0, 1, H)[:, None, None]
    g = np.array(top)[None, None, :] * (1 - y) + np.array(bot)[None, None, :] * y
    return np.broadcast_to(g, (H, W, 3)).astype(np.float32)
NIGHT = vgrad((6, 7, 14), (16, 14, 26))
HEAT = vgrad((14, 6, 10), (40, 10, 16))
yy, xx = np.mgrid[0:H, 0:W]
rr = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.68)) ** 2)
VIG = np.clip(1.15 - 0.6 * rr ** 2, 0.3, 1.0)[..., None].astype(np.float32)
GLOW = np.exp(-(((xx - W * 0.5) / (W * 0.55)) ** 2 + ((yy - H * 0.42) / (H * 0.3)) ** 2))[..., None].astype(np.float32)
rng = np.random.default_rng(3)
GRAIN = [rng.normal(0, 4.5, (H, W, 1)).astype(np.float32) for _ in range(6)]

def tw(font, s): return font.getlength(s)
def ctext(d, y, s, font, fill, x0=0, x1=W):
    d.text((x0 + (x1 - x0 - tw(font, s)) / 2, y), s, font=font, fill=fill)
def wrap(text, font, maxw):
    out, cur = [], ""
    for w_ in text.split():
        t = (cur + " " + w_).strip()
        if tw(font, t) <= maxw: cur = t
        else: out.append(cur); cur = w_
    out.append(cur); return out
def alpha(layer, a):
    if a >= 1: return layer
    l = layer.copy(); l.putalpha(layer.getchannel("A").point(lambda v: int(v * a))); return l
def paste(base, layer, a, xy=(0, 0)):
    if a > 0: base.alpha_composite(alpha(layer, a), (int(xy[0]), int(xy[1])))

def rrect(size, r, fill, outline=None, width=2):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=fill, outline=outline, width=width)
    return im

def caption(base, t, a, b, text, y, font=None, fill=WHITE):
    k = win(t, a, b)
    if k <= 0: return
    font = font or I("InterDisplay-SemiBold.otf", 62)
    lines = wrap(text, font, W - 160)
    lay = Image.new("RGBA", (W, 90 * len(lines) + 20), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for i, ln in enumerate(lines):
        ctext(d, i * int(font.size * 1.2), ln, font, fill)
    paste(base, lay, k, (0, y + 18 * (1 - k)))

# ---------- product: a tee for the fictional drop ----------
def tee(size=520):
    S = size * 2; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    s = S / 100
    pts = [(30, 12), (40, 8), (44, 13), (56, 13), (60, 8), (70, 12), (90, 26), (82, 40), (73, 35), (73, 92), (27, 92), (27, 35), (18, 40), (10, 26)]
    d.polygon([(x * s, y * s) for x, y in pts], fill=(18, 18, 22, 255))
    d.line([(x * s, y * s) for x, y in pts + [pts[0]]], fill=(60, 60, 70, 255), width=int(s * 0.5))
    d.arc((40 * s, 4 * s, 60 * s, 20 * s), 20, 160, fill=(70, 70, 80, 255), width=int(s * 0.8))
    f = B(int(16 * s)); txt = "KAIRO"
    d.text((50 * s - f.getlength(txt) / 2, 40 * s), txt, font=f, fill=(*GOLD, 255))
    f2 = M(int(3.2 * s)); t2 = "DROP 001  ·  NO RESTOCKS"
    d.text((50 * s - f2.getlength(t2) / 2, 60 * s), t2, font=f2, fill=(200, 200, 210, 255))
    return im.resize((size, size), Image.LANCZOS)
TEE = tee()

def post_card(views, likes, pulse=0.0):
    cw, ch = 860, 1120
    c = rrect((cw, ch), 40, (*CARD, 255), (*LINE, 255))
    d = ImageDraw.Draw(c)
    d.ellipse((40, 40, 120, 120), fill=(*GOLD, 255)); d.text((62, 52), "K", font=B(56), fill=INK)
    d.text((142, 48), "kairo.studio", font=I("Inter-SemiBold.otf", 36), fill=WHITE)
    d.text((142, 92), "Posted 1h ago", font=I("Inter-Regular.otf", 28), fill=MUT)
    ph = rrect((cw - 80, 720), 26, (30, 30, 40, 255))
    g = Image.new("RGBA", ph.size, (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
    gd.ellipse((90, 60, cw - 170, 680), fill=(251, 191, 36, 34)); g = g.filter(ImageFilter.GaussianBlur(60))
    ph.alpha_composite(g); ph.alpha_composite(TEE, ((cw - 80 - 520) // 2, 110))
    m = Image.new("L", ph.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, ph.size[0] - 1, ph.size[1] - 1), 26, fill=255)
    ph.putalpha(m); c.alpha_composite(ph, (40, 150))
    d.text((40, 900), "DROP 001 IS LIVE. Link in bio.", font=I("Inter-SemiBold.otf", 38), fill=WHITE)
    vf = M(44)
    col = tuple(int(MUT[i] + (RED[i] - MUT[i]) * pulse) for i in range(3))
    d.text((40, 980), f"{views} views", font=vf, fill=col)
    d.text((40 + tw(vf, f"{views} views") + 50, 980), f"{likes} likes", font=vf, fill=MUT)
    return c

# ---------- chat ----------
def bubble(text, mine, font=None, maxw=700):
    font = font or I("Inter-Regular.otf", 44)
    lines = wrap(text, font, maxw); lh = int(font.size * 1.28)
    bw = int(max(tw(font, l) for l in lines)) + 60; bh = lh * len(lines) + 40
    col = (*RED, 255) if mine else (40, 40, 54, 255)
    b = rrect((bw, bh), 34, col); d = ImageDraw.Draw(b)
    for i, l in enumerate(lines): d.text((30, 18 + i * lh), l, font=font, fill=WHITE if not mine else (255, 255, 255))
    return b

def chat_header(name, sub):
    h = Image.new("RGBA", (W, 200), (12, 12, 18, 235)); d = ImageDraw.Draw(h)
    d.text((60, 30), "1:09", font=I("Inter-SemiBold.otf", 34), fill=WHITE)
    d.text((60, 104), "<", font=I("Inter-Regular.otf", 52), fill=CYAN)
    d.ellipse((120, 96, 190, 166), fill=(*CYAN, 255)); d.text((141, 101), name[0], font=B(56), fill=INK)
    d.text((212, 100), name, font=I("Inter-SemiBold.otf", 40), fill=WHITE)
    d.text((212, 146), sub, font=I("Inter-Regular.otf", 26), fill=MUT)
    d.line((0, 199, W, 199), fill=LINE, width=2)
    return h

# ---------- clips from real ads ----------
PW, PH = 640, 1138
def load_clip(path, start, dur):
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", str(start), "-t", str(dur), "-i", path,
           "-vf", f"scale={PW}:{PH},fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (PW * PH * 3)
    return np.frombuffer(raw[: n * PW * PH * 3], np.uint8).reshape(n, PH, PW, 3)
CLIPS = {}
def clips():
    if CLIPS: return
    CLIPS["ark"] = load_clip(os.path.join(REPO, "assets/ads/newark-microdrama.mp4"), 12.6, 3.0)
    CLIPS["fr"] = load_clip(os.path.join(REPO, "assets/ads/friendy-microdrama.mp4"), 15.0, 3.0)
    hero = Image.open(os.path.join(REPO, "assets/clients/hsw365-ledmask/hero.png")).convert("RGB")
    s = max(PW / hero.width, PH / hero.height) * 1.2
    CLIPS["led"] = hero.resize((int(hero.width * s), int(hero.height * s)), Image.LANCZOS)

PHONE_MASK = Image.new("L", (PW, PH), 0); ImageDraw.Draw(PHONE_MASK).rounded_rectangle((0, 0, PW - 1, PH - 1), 44, fill=255)
def phone(frame_img):
    ow, oh = PW + 28, PH + 28
    p = rrect((ow, oh), 58, (34, 34, 44, 255), (70, 70, 84, 255), 3)
    fi = frame_img.convert("RGBA"); fi.putalpha(PHONE_MASK); p.alpha_composite(fi, (14, 14))
    return p

def led_frame(lt):
    im = CLIPS["led"]; z = 1.0 + 0.06 * lt
    w, h = int(PW * 1.2 / z), int(PH * 1.2 / z)
    w, h = min(w, im.width), min(h, im.height)
    x = (im.width - w) // 2; y = int((im.height - h) * 0.4)
    return im.crop((x, y, x + w, y + h)).resize((PW, PH), Image.LANCZOS)

# ---------- QR ----------
def qr_card(box=420):
    import segno
    buf = io.BytesIO(); segno.make(URL, error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
    code = Image.open(buf).convert("RGBA").resize((box - 60, box - 60), Image.NEAREST)
    c = rrect((box, box), 36, (255, 255, 255, 255)); c.alpha_composite(code, (30, 30))
    badge = rrect((96, 96), 22, (*RED, 255)); bd = ImageDraw.Draw(badge)
    bf = B(66); bd.text(((96 - tw(bf, "A")) / 2, 6), "A", font=bf, fill=INK)
    wb = rrect((112, 112), 26, (255, 255, 255, 255)); wb.alpha_composite(badge, (8, 8))
    c.alpha_composite(wb, ((box - 112) // 2, (box - 112) // 2))
    return c
QR = qr_card()

STEPS = [("01", "FIND THE SCENE", "Your customer's worst moment"),
         ("02", "SCRIPT IT", "Hook. Tension. The turn. You."),
         ("03", "PRODUCE IT", "Cinematic frames, captions, sound"),
         ("04", "QR + POST IT", "iRun posts it to your Instagram")]

def finish(arr, i):
    arr = arr * VIG + GRAIN[i % 6]
    return np.clip(arr, 0, 255).astype(np.uint8)

def frame(i):
    t = i / FPS
    # background
    if t < 11.0: bg = NIGHT.copy()
    elif t < 24.4: bg = NIGHT * 0.9 + HEAT * 0.1 + GLOW * np.array([60, 14, 18], np.float32) * win(t, 11.0, 24.4, 0.6, 0.6)
    else: bg = NIGHT * 0.6 + HEAT * 0.4
    base = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(base)

    # A: 1:07 AM
    k = win(t, 0.2, 3.7, 0.6, 0.4)
    if k:
        lay = Image.new("RGBA", (W, 600), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "Friday, drop night", I("Inter-Medium.otf", 44), MUT)
        ctext(ld, 60, "1:07", I("InterDisplay-Thin.otf", 300), WHITE)
        paste(base, lay, k, (0, 560))
        caption(base, t, 1.0, 3.7, "Three weeks building her clothing line.", 1300, I("InterDisplay-Medium.otf", 54), (210, 210, 222))

    # B: the post that nobody saw
    k = win(t, 3.6, 8.1, 0.45, 0.35)
    if k:
        views = 12 + int(clamp((t - 4.4) / 3.0) * 2)
        pulse = clamp(1 - abs(t - 6.6) / 0.5) if t > 6.1 else 0
        card = post_card(views, 2, pulse)
        s = 0.96 + 0.04 * ease((t - 3.6) / 4.5)
        card = card.resize((int(card.width * s), int(card.height * s)), Image.LANCZOS)
        paste(base, card, k, ((W - card.width) / 2, 300 - 20 * (1 - k)))
        caption(base, t, 5.0, 8.1, "14 views. Zero sales.", 1530, I("InterDisplay-SemiBold.otf", 66))

    # C: the text from Dre
    k = win(t, 8.0, 11.1, 0.3, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(chat_header("Dre", "online"), (0, 0))
        b1 = bubble("yo you seen the ads Hoodstar been making??", False)
        b2 = bubble("they not flyers. they're movies.", False)
        b3 = bubble("send me one", True)
        y = 300
        for bb, ts, mine in ((b1, 8.25, False), (b2, 9.1, False), (b3, 10.0, True)):
            if t >= ts:
                a = ease((t - ts) / 0.22); x = W - 60 - bb.width if mine else 60
                lay.alpha_composite(alpha(bb, a), (int(x), int(y + 20 * (1 - a))))
            y += bb.height + 26
        paste(base, lay, k)

    # D: real ads playing
    if 10.9 <= t < 19.9:
        clips()
        segs = [("ark", 11.0, 14.0, "NEW ARK PLUMBING", "Home services"),
                ("fr", 14.0, 17.0, "FRIENDY", "App launch"),
                ("led", 17.0, 19.8, "LED PHOTON MASK", "E-commerce")]
        for key, a0, a1, name, kind in segs:
            if a0 - 0.1 <= t < a1:
                lt = t - a0
                if key == "led": img = led_frame(lt / 3)
                else:
                    arr = CLIPS[key]; img = Image.fromarray(arr[min(len(arr) - 1, max(0, int(lt * FPS)))])
                ph = phone(img)
                ka = min(ease(lt / 0.3), ease((a1 - t) / 0.25)) if key != "ark" else min(ease((t - 10.9) / 0.4), ease((a1 - t) / 0.25))
                sc = 0.93 + 0.07 * ease(lt / 0.5)
                ph2 = ph.resize((int(ph.width * sc), int(ph.height * sc)), Image.LANCZOS)
                paste(base, ph2, ka, ((W - ph2.width) / 2, 330 + (ph.height - ph2.height) / 2))
                lay = Image.new("RGBA", (W, 220), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
                ctext(ld, 0, kind.upper(), M(30), MUT)
                ctext(ld, 44, name, B(104), WHITE)
                paste(base, lay, ka, (0, 110))
        caption(base, t, 11.3, 19.8, "Real ads. Real businesses.", 1560, I("InterDisplay-SemiBold.otf", 62))
        caption(base, t, 11.6, 19.8, "Made by HSW365. Posted by iRun.", 1650, I("InterDisplay-Medium.otf", 44), MUT)

    # E: how they're made
    k = win(t, 19.8, 24.5, 0.35, 0.35)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 250, "HOW WE MAKE THEM", M(40), RED)
        y = 400
        for n, (num, head, sub) in enumerate(STEPS):
            ts = 20.1 + n * 0.85
            if t >= ts:
                a = ease((t - ts) / 0.3)
                row = Image.new("RGBA", (W, 260), (0, 0, 0, 0)); rd = ImageDraw.Draw(row)
                rd.text((110, 10), num, font=M(54), fill=RED)
                rd.text((250, -8), head, font=B(112), fill=WHITE)
                rd.text((254, 118), sub, font=I("Inter-Medium.otf", 40), fill=(200, 200, 214))
                rd.line((110, 210, W - 110, 210), fill=LINE, width=2)
                lay.alpha_composite(alpha(row, a), (int(-40 * (1 - a)), y))
            y += 270
        paste(base, lay, k)

    # F: price text
    k = win(t, 24.4, 26.8, 0.3, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(chat_header("HSW365 Ad Studio", "replies fast"), (0, 0))
        b1 = bubble("how much for my clothing line??", True)
        b2 = bubble("Ads from $247. Scripted, produced, QR on the end, posted to your IG.", False)
        y = 300
        for bb, ts, mine in ((b1, 24.5, True), (b2, 25.25, False)):
            if t >= ts:
                a = ease((t - ts) / 0.22); x = W - 60 - bb.width if mine else 60
                lay.alpha_composite(alpha(bb, a), (int(x), int(y + 20 * (1 - a))))
            y += bb.height + 26
        paste(base, lay, k)

    # G: end card
    k = win(t, 26.6, 31, 0.45, 0.1)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 150, "HSW365", M(44), RED)
        ctext(ld, 205, "AD STUDIO", B(190), WHITE)
        ctext(ld, 420, "Micro-drama ads for your business,", I("InterDisplay-Medium.otf", 44), (210, 210, 222))
        ctext(ld, 478, "your clothing line, your music.", I("InterDisplay-Medium.otf", 44), (210, 210, 222))
        lay.alpha_composite(QR, ((W - QR.width) // 2, 600))
        ctext(ld, 1050, "SCAN TO BOOK YOUR AD", B(64), CYAN)
        tiers = [("SCENE", "$247"), ("SERIES", "$1,247"), ("TAKEOVER", "$3,597/mo")]
        cw = 300; gx = (W - cw * 3 - 30) // 2
        for n, (nm, pr) in enumerate(tiers):
            c = rrect((cw, 170), 24, (*CARD, 255), (*(RED if n == 1 else LINE), 255), 3)
            cd = ImageDraw.Draw(c); ctext(cd, 26, nm, M(28), MUT, 0, cw); ctext(cd, 72, pr, M(46 if n < 2 else 38), WHITE, 0, cw)
            lay.alpha_composite(c, (gx + n * (cw + 15), 1180))
        ctext(ld, 1420, "hsw365.github.io/iRUN/adstudio", M(36), WHITE)
        ctext(ld, 1480, "Pay with Cash App or Zelle  ·  72-hour delivery", I("Inter-Medium.otf", 34), MUT)
        ctext(ld, 1720, "HSW365 Media  ·  Turn Negative Into Positive", I("Inter-Medium.otf", 30), (120, 120, 140))
        paste(base, lay, k, (0, 20 * (1 - k)))

    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < 0.5: arr *= clamp(t / 0.5)
    if t > 29.6: arr *= clamp((30 - t) / 0.4)
    # quick flash cuts
    for tc in (3.6, 8.0, 11.0, 19.8, 24.4, 26.6):
        if 0 <= t - tc < 0.12: arr = arr * 0.6 + 255 * 0.4 * (1 - (t - tc) / 0.12)
    return finish(arr, i)

# ---------- audio ----------
def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr; a = np.zeros(n)
    # cold drone, first 11s
    a += (0.05 * np.sin(2 * np.pi * 55 * tt) + 0.03 * np.sin(2 * np.pi * 82.4 * tt)) * np.clip(tt / 1.5, 0, 1) * np.clip((11 - tt) / 0.6, 0, 1)
    # slow heartbeat 0-8s
    def thump(t0, amp):
        i0 = int(t0 * sr); m = int(0.25 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += amp * np.sin(2 * np.pi * (60 - 40 * x) * x) * np.exp(-x * 18)
    for b in np.arange(0.5, 8.0, 1.0): thump(b, 0.35); thump(b + 0.22, 0.22)
    # beat from 11.0 to 29.5 at 92 bpm
    spb = 60 / 92
    def kick(t0):
        i0 = int(t0 * sr); m = int(0.35 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += 0.6 * np.sin(2 * np.pi * (110 * np.exp(-x * 20) + 45) * x) * np.exp(-x * 7)
    def hat(t0, amp=0.05):
        i0 = int(t0 * sr); m = int(0.05 * sr)
        if i0 + m < n: a[i0:i0 + m] += amp * rng.normal(0, 1, m) * np.exp(-np.arange(m) / sr * 80)
    def snare(t0):
        i0 = int(t0 * sr); m = int(0.2 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += (0.18 * rng.normal(0, 1, m) + 0.2 * np.sin(2 * np.pi * 190 * x)) * np.exp(-x * 22)
    bass_notes = [55.0, 55.0, 65.4, 49.0]
    beat = 0; tb = 11.0
    while tb < 29.3:
        if beat % 4 in (0,) or beat % 8 == 6: kick(tb)
        if beat % 4 == 2: snare(tb)
        hat(tb + spb / 2); hat(tb, 0.03)
        i0 = int(tb * sr); m = int(spb * sr); x = np.arange(m) / sr
        f = bass_notes[(beat // 4) % 4]
        if i0 + m < n: a[i0:i0 + m] += 0.12 * np.sin(2 * np.pi * f * x) * np.exp(-x * 2.5)
        tb += spb; beat += 1
    # pads under end card
    for f in (220.0, 277.2, 329.6):
        a += 0.03 * np.sin(2 * np.pi * f * tt) * np.clip((tt - 26.6) / 1.0, 0, 1) * np.clip((29.8 - tt) / 0.6, 0, 1)
    # whooshes on cuts
    for tc in (3.6, 8.0, 11.0, 19.8, 24.4, 26.6):
        i0 = int((tc - 0.25) * sr); m = int(0.5 * sr); x = np.arange(m) / sr
        env = np.sin(np.pi * x / 0.5) ** 2
        a[i0:i0 + m] += 0.12 * np.convolve(rng.normal(0, 1, m), np.ones(12) / 12, "same") * env
    # message pops
    for p in (8.25, 9.1, 10.0, 24.5, 25.25):
        i0 = int(p * sr); m = int(0.09 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.18 * np.sin(2 * np.pi * (950 - 3000 * x) * x) * np.exp(-x * 45)
    # step ticks
    for k in range(4):
        i0 = int((20.1 + k * 0.85) * sr); m = int(0.06 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.12 * np.sin(2 * np.pi * 1400 * x) * np.exp(-x * 60)
    a *= np.clip((DUR - tt) / 0.6, 0, 1)
    a = np.clip(a / max(1e-6, np.max(np.abs(a))) * 0.85, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    out = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "preview":
        for ts in [float(x) for x in sys.argv[3].split(",")]:
            Image.fromarray(frame(int(ts * FPS))).save(f"{out}_{ts:.1f}.png")
        sys.exit()
    wav = out + ".wav"; audio(wav)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-b:v", "7M", "-maxrate", "8M", "-bufsize", "16M",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i in range(N): p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait(); os.remove(wav); print("done", out)
