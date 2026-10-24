"""Klipit micro-drama ad: "Somebody Clip That" — 30s, 1080x1920, 30fps.
A streamer hits the moment of his life on a GTA 6 stream, nobody clips it, he loses it in a 6-hour VOD,
and a stranger posts it first. Next stream he pastes the link into Klipit. Ends on a scan-to-subscribe QR.
Original visuals only: no game footage, logos or trademarked art.
Usage: python klipit_render.py out.mp4            (full render)
       python klipit_render.py out preview 4,12,26 (stills)"""
import io, math, os, subprocess, sys, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1080, 1920, 30, 30.0
N = int(FPS * DUR)
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "fonts")
INTER = "/usr/share/fonts/opentype/inter/"
SITE = "https://klipit.onrender.com/"

def FB(name, size): return ImageFont.truetype(os.path.join(FONTS, name), size)
def FI(name, size):
    try: return ImageFont.truetype(INTER + name, size)
    except OSError: return FB("BarlowCondensed-SemiBold.ttf", size)

f_huge = FB("BarlowCondensed-ExtraBold.ttf", 230)
f_big = FB("BarlowCondensed-ExtraBold.ttf", 120)
f_cap = FB("BarlowCondensed-ExtraBold.ttf", 92)
f_capS = FB("BarlowCondensed-SemiBold.ttf", 64)
f_lab = FB("BarlowCondensed-SemiBold.ttf", 44)
f_mono = FB("SpaceMono-Bold.ttf", 36)
f_monoS = FB("SpaceMono-Bold.ttf", 28)
f_monoL = FB("SpaceMono-Bold.ttf", 64)
f_chatU = FI("Inter-Bold.otf", 38)
f_chat = FI("Inter-Medium.otf", 38)
f_ui = FI("Inter-SemiBold.otf", 40)
f_uiS = FI("Inter-Medium.otf", 32)
f_uiB = FI("Inter-Bold.otf", 46)

BASE = (10, 10, 15); CYAN = (34, 211, 238); VIOLET = (168, 85, 247); RED = (239, 68, 68); YEL = (251, 191, 36)
WHITE = (245, 246, 250); MUTED = (140, 146, 170)

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_io(x): x = clamp(x); return 3 * x * x - 2 * x * x * x
def win(t, a, b, fi=0.35, fo=0.35):
    if t < a or t > b: return 0.0
    return min(ease((t - a) / fi) if fi else 1, ease((b - t) / fo) if fo else 1)

def paste_alpha(base, layer, a, xy=(0, 0)):
    if a <= 0: return
    if a < 1:
        layer = layer.copy(); layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
    base.alpha_composite(layer, (int(xy[0]), int(xy[1])))

def wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if font.getlength(test) <= maxw: cur = test
        else: lines.append(cur); cur = w_
    lines.append(cur); return lines

def glow_text(text, font, fill, blur=18, strength=1.0, glow=None):
    w_ = int(font.getlength(text)) + blur * 4; h_ = int(font.size * 1.35) + blur * 4
    lay = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
    m = Image.new("L", (w_, h_), 0); ImageDraw.Draw(m).text((blur * 2, blur * 2), text, font=font, fill=255)
    g = Image.new("RGBA", (w_, h_), (glow or fill) + (0,))
    g.putalpha(m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(min(255, v * 1.6 * strength))))
    lay.alpha_composite(g)
    s = Image.new("RGBA", (w_, h_), fill + (0,)); s.putalpha(m); lay.alpha_composite(s)
    return lay

def caption(base, t, a, b, text, y, font=None, color=WHITE, maxw=940):
    al = win(t, a, b, 0.4, 0.4)
    if al <= 0: return
    font = font or f_cap
    lines = wrap(text, font, maxw); lh = font.size * 1.08
    lay = Image.new("RGBA", (W, int(len(lines) * lh + 60)), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for i, l in enumerate(lines):
        d.text(((W - font.getlength(l)) / 2, 20 + i * lh), l, font=font, fill=color + (255,))
    sh = Image.new("RGBA", lay.size, (0, 0, 0, 0)); sh.putalpha(lay.getchannel("A").filter(ImageFilter.GaussianBlur(16)))
    rise = (1 - ease((t - a) / 0.5)) * 26
    paste_alpha(base, sh, al, (0, y + rise)); paste_alpha(base, sh, al * 0.7, (0, y + rise)); paste_alpha(base, lay, al, (0, y + rise))

# ---------- the "game view": original neon night-city chase, procedurally drawn ----------
GH = 1060  # game view height in the vertical stream layout
rng = np.random.default_rng(365)
def build_sky():
    y = np.linspace(0, 1, GH)[:, None, None]
    top = np.array((12, 8, 32)); mid = np.array((70, 22, 92)); hor = np.array((236, 72, 120))
    g = np.where(y < 0.55, top * (1 - y / 0.55) + mid * (y / 0.55), mid * (1 - (y - 0.55) / 0.45) + hor * ((y - 0.55) / 0.45))
    return Image.fromarray(np.broadcast_to(g, (GH, W, 3)).astype(np.uint8), "RGB").convert("RGBA")
SKY = build_sky()
HORIZON = 600
def build_skyline(seed, scale, col, lit):
    r = np.random.default_rng(seed)
    img = Image.new("RGBA", (W * 2, GH), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    x = 0
    while x < W * 2:
        bw = int(r.integers(60, 150) * scale); bh = int(r.integers(120, 430) * scale)
        d.rectangle((x, HORIZON - bh, x + bw, HORIZON + 4), fill=col)
        if lit:
            for wy in range(HORIZON - bh + 18, HORIZON - 10, 26):
                for wx in range(x + 12, x + bw - 12, 22):
                    if r.random() < 0.32:
                        c = (255, 214, 140, 200) if r.random() < 0.7 else (34, 211, 238, 200)
                        d.rectangle((wx, wy, wx + 8, wy + 12), fill=c)
        if r.random() < 0.3:
            d.rectangle((x + bw // 2 - 2, HORIZON - bh - 60, x + bw // 2 + 2, HORIZON - bh), fill=col)
        x += bw + int(r.integers(0, 14))
    return img
FAR = build_skyline(1, 0.75, (34, 14, 58, 255), False)
NEAR = build_skyline(2, 1.0, (14, 10, 26, 255), True)
SUN = Image.new("RGBA", (520, 520), (0, 0, 0, 0))
_m = Image.new("L", (520, 520), 0); ImageDraw.Draw(_m).ellipse((60, 60, 460, 460), fill=255)
_s = Image.new("RGBA", (520, 520), (255, 140, 90, 0)); _s.putalpha(_m.filter(ImageFilter.GaussianBlur(40)).point(lambda v: int(v * 0.55)))
SUN.alpha_composite(_s); _c = Image.new("RGBA", (520, 520), (255, 170, 110, 255)); _m2 = Image.new("L", (520, 520), 0)
ImageDraw.Draw(_m2).ellipse((110, 110, 410, 410), fill=255)
for k in range(8): ImageDraw.Draw(_m2).rectangle((0, 270 + k * 18, 520, 270 + k * 18 + 3 + k), fill=0)
_c.putalpha(_m2); SUN.alpha_composite(_c)

def car_sprite(w_, col, lights):
    h_ = int(w_ * 0.42)
    img = Image.new("RGBA", (w_ + 40, h_ + 40), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20 + h_ * 0.35, 20 + w_, 20 + h_), 14, fill=col)
    d.polygon([(20 + w_ * 0.2, 20 + h_ * 0.38), (20 + w_ * 0.3, 20), (20 + w_ * 0.7, 20), (20 + w_ * 0.8, 20 + h_ * 0.38)], fill=tuple(int(c * 0.7) for c in col[:3]) + (255,))
    d.polygon([(20 + w_ * 0.27, 20 + h_ * 0.34), (20 + w_ * 0.34, 28), (20 + w_ * 0.66, 28), (20 + w_ * 0.73, 20 + h_ * 0.34)], fill=(20, 24, 40, 255))
    for lx in (20 + w_ * 0.06, 20 + w_ * 0.8):
        d.rounded_rectangle((lx, 20 + h_ * 0.52, lx + w_ * 0.14, 20 + h_ * 0.66), 5, fill=lights)
    d.rectangle((20 + w_ * 0.36, 20 + h_ * 0.7, 20 + w_ * 0.64, 20 + h_ * 0.82), fill=(230, 230, 240, 255))
    return img
HERO = car_sprite(300, (24, 26, 34, 255), (255, 50, 70, 255))
COP = car_sprite(200, (230, 232, 240, 255), (255, 50, 70, 255))

def game_view(t, heat=0.0, frozen=None, shake=0.0):
    tt = frozen if frozen is not None else t
    g = SKY.copy()
    g.alpha_composite(SUN, (W // 2 - 260, HORIZON - 330))
    ox = int((tt * 40) % W); g.alpha_composite(FAR, (-ox, 0))
    ox2 = int((tt * 110) % W); g.alpha_composite(NEAR, (-ox2, 0))
    d = ImageDraw.Draw(g)
    d.rectangle((0, HORIZON, W, GH), fill=(14, 10, 24, 255))
    vx = W // 2
    d.polygon([(vx - 30, HORIZON), (vx + 30, HORIZON), (W + 380, GH), (-380, GH)], fill=(26, 22, 40, 255))
    for side in (-1, 1):
        d.line([(vx + side * 30, HORIZON), (W // 2 + side * 900, GH)], fill=(34, 211, 238, 200), width=5)
    speed = 2.2 + heat * 2.5
    for k in range(10):
        p = ((k / 10) + tt * speed * 0.18) % 1.0
        z0 = p ** 2.2; z1 = min(1, (p + 0.04) ** 2.2)
        y0 = HORIZON + z0 * (GH - HORIZON); y1 = HORIZON + z1 * (GH - HORIZON)
        w0 = 3 + z0 * 22
        d.polygon([(vx - w0, y0), (vx + w0, y0), (vx + w0 * 1.3, y1), (vx - w0 * 1.3, y1)], fill=(251, 191, 36, 230))
    for k in range(14):  # street lights streaking past
        p = ((k / 14) + tt * speed * 0.12) % 1.0
        z = p ** 2.4; y = HORIZON - 10 - z * 520; x = vx + (1 if k % 2 else -1) * (40 + z * 760)
        r_ = 2 + z * 14
        d.ellipse((x - r_, y - r_, x + r_, y + r_), fill=(255, 220, 160, int(140 + 100 * z)))
    if heat > 0:
        n_cops = 1 + int(heat * 2.2)
        for c in range(n_cops):
            cx = vx + (c - (n_cops - 1) / 2) * 260 + math.sin(tt * 2 + c) * 30
            cy = 700 + c % 2 * 30
            g.alpha_composite(COP, (int(cx - COP.width / 2), int(cy)))
            bar = Image.new("RGBA", (120, 30), (0, 0, 0, 0)); bd = ImageDraw.Draw(bar)
            ph = (tt * 6 + c) % 1 < 0.5
            bd.rectangle((0, 0, 58, 22), fill=(239, 68, 68, 255) if ph else (60, 20, 30, 255))
            bd.rectangle((62, 0, 120, 22), fill=(60, 120, 255, 255) if not ph else (20, 30, 60, 255))
            g.alpha_composite(bar, (int(cx - 60), int(cy + 8)))
    sway = math.sin(tt * 3.1) * 40 * (0.4 + heat)
    g.alpha_composite(HERO, (int(vx - HERO.width / 2 + sway), 820))
    if heat > 0:
        ph = (tt * 4) % 1
        col = (239, 68, 68) if ph < 0.5 else (60, 120, 255)
        fl = Image.new("RGBA", (W, GH), col + (int(70 * heat * (0.5 + 0.5 * math.sin(tt * 25))),))
        g.alpha_composite(fl)
    if shake:
        dx = int(rng.normal(0, shake)); dy = int(rng.normal(0, shake))
        g = g.transform(g.size, Image.AFFINE, (1, 0, dx, 0, 1, dy), resample=Image.BILINEAR)
    return g

# ---------- stream chrome ----------
def fmt_hms(s):
    s = int(s); return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"

def live_hud(lay, t, uptime, viewers, ended=False):
    d = ImageDraw.Draw(lay)
    pill = (239, 68, 68) if not ended else (80, 84, 100)
    d.rounded_rectangle((44, 52, 194, 106), 12, fill=pill)
    d.text((66, 56), "LIVE" if not ended else "OFF", font=f_lab, fill=WHITE)
    d.text((214, 60), fmt_hms(uptime), font=f_mono, fill=WHITE)
    vs = f"{viewers:,} watching"
    d.text((W - 44 - f_uiS.getlength(vs), 62), vs, font=f_uiS, fill=WHITE)

USERS = [("tre_nyc", CYAN), ("lowkeyRico", YEL), ("mxrcy", VIOLET), ("dblock_dre", (110, 231, 183)), ("kiaaa", (255, 138, 138)),
         ("vibezOnly", CYAN), ("jaythe3rd", YEL), ("sosa_tv", VIOLET), ("bigmike856", (110, 231, 183)), ("nana.k", (255, 138, 138))]
CALM = ["he not making it out", "turn left turn LEFT", "6 hours deep lmao", "go to sleep bro", "nah this map crazy",
        "he been driving for 20 min", "who else up at 3am", "W stream", "lag?", "bro thinks he's in a movie"]
HYPE = ["NO WAY", "CLIP THAT", "SOMEBODY CLIP IT", "BROOOOO", "CLIPPPPP", "NAHHHH", "HE REALLY DID THAT", "CLIP IT CLIP IT",
        "ARE YOU SERIOUS", "MOD CLIP THAT", "THAT'S GOING VIRAL", "INSANE"]
def chat_lines(t):
    out = []; k = 0; tc = 0.0
    while tc < t:
        hype = 3.6 <= tc <= 8.2
        out.append((tc, USERS[k % len(USERS)], (HYPE if hype else CALM)[(k * 7) % (len(HYPE) if hype else len(CALM))], hype))
        k += 1; tc += 0.16 if hype else 0.75
    return out[-9:]

def chat_panel(lay, t, top):
    d = ImageDraw.Draw(lay)
    d.rectangle((0, top, W, H), fill=(13, 13, 20, 255))
    d.line([(0, top), (W, top)], fill=(34, 211, 238, 90), width=2)
    d.text((44, top + 22), "STREAM CHAT", font=f_lab, fill=MUTED)
    lines = chat_lines(t); y = top + 96
    for (ts, (u, uc), msg, hype) in lines:
        a = ease((t - ts) / 0.15)
        d.text((44, y), u, font=f_chatU, fill=tuple(int(c * a) for c in uc))
        mx = 44 + f_chatU.getlength(u) + 18
        col = WHITE if not hype else (255, 230, 120)
        d.text((mx, y), msg, font=f_chat if not hype else f_chatU, fill=tuple(int(c * a) for c in col))
        y += 62

def vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.8)) ** 2 + ((yy - H / 2) / (H * 0.72)) ** 2)
    return np.clip(1.12 - 0.5 * r ** 2, 0.4, 1.0)[..., None].astype(np.float32)
VIG = vignette()
GRAIN = [np.random.default_rng(s).normal(0, 4.5, (H, W, 1)).astype(np.float32) for s in range(6)]

# ---------- VOD scrubber ----------
VOD_LEN = 6 * 3600 + 42 * 60 + 17
SCRUB = [(10.9, 0.12), (11.6, 0.71), (12.2, 0.33), (12.8, 0.88), (13.4, 0.52), (14.0, 0.18), (14.5, 0.63), (15.0, 0.41)]
def scrub_pos(t):
    prev = 0.0
    for ts, p in SCRUB:
        if t < ts: return prev
        prev = p
    return prev

def vod_scene(base, t):
    p = scrub_pos(t)
    gv = game_view(t, 0.0, frozen=p * 400).convert("RGB").filter(ImageFilter.GaussianBlur(2)).convert("RGBA")
    dark = Image.new("RGBA", gv.size, (0, 0, 0, 120)); gv.alpha_composite(dark)
    base.alpha_composite(gv, (0, 300))
    d = ImageDraw.Draw(base)
    d.rectangle((0, 300, W, 300 + GH), outline=(40, 44, 60), width=2)
    d.text((44, 210), "PAST BROADCAST", font=f_lab, fill=MUTED)
    # timeline
    ty = 300 + GH - 90
    d.rounded_rectangle((60, ty, W - 60, ty + 14), 7, fill=(60, 64, 82))
    px = 60 + p * (W - 120)
    d.rounded_rectangle((60, ty, px, ty + 14), 7, fill=(239, 68, 68))
    d.ellipse((px - 22, ty - 15, px + 22, ty + 29), fill=WHITE)
    lab = f"{fmt_hms(p * VOD_LEN)} / {fmt_hms(VOD_LEN)}"
    d.text((60, ty - 70), lab, font=f_mono, fill=WHITE)
    # thumbnail preview over scrubber
    for ts, _ in SCRUB:
        if 0 <= t - ts < 0.35:
            a = 1 - (t - ts) / 0.35
            th = game_view(ts, 0.0, frozen=scrub_pos(t) * 400).resize((300, 294), Image.BILINEAR)
            card = Image.new("RGBA", (310, 304), (255, 255, 255, 255)); card.alpha_composite(th, (5, 5))
            paste_alpha(base, card, 0.5 + 0.5 * a, (clamp(px - 155, 30, W - 340), ty - 400))
    # time-wasted counter
    elapsed = 3600 + (t - 10.6) / 6.2 * 6720
    d.text((44, 1520), "LOOKING FOR IT", font=f_lab, fill=(239, 68, 68))
    d.text((44, 1570), fmt_hms(max(3600, elapsed)), font=f_monoL, fill=WHITE)

def notification(base, t, t0):
    p = ease((t - t0) / 0.45)
    w_, h_ = 980, 250
    lay = Image.new("RGBA", (w_, h_), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w_ - 1, h_ - 1), 44, fill=(30, 30, 44, 245), outline=(239, 68, 68, 160), width=3)
    d.rounded_rectangle((36, 40, 116, 120), 22, fill=VIOLET)
    d.text((58, 50), "R", font=f_uiB, fill=WHITE)
    d.text((140, 36), "Reels", font=f_ui, fill=WHITE)
    d.text((w_ - 110, 40), "now", font=f_uiS, fill=MUTED)
    d.text((140, 92), "@clipfarm_daily posted your moment", font=f_uiS, fill=(220, 222, 235))
    d.text((140, 140), "\"Streamer pulls off impossible getaway\"", font=f_uiS, fill=(220, 222, 235))
    d.text((140, 188), "2.1M views", font=f_ui, fill=(239, 68, 68))
    paste_alpha(base, lay, p, ((W - w_) // 2, 80 + (1 - p) * -240))

# ---------- Klipit UI ----------
def k_logo(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), size // 4, fill=CYAN)
    f = FB("BarlowCondensed-ExtraBold.ttf", int(size * 0.8))
    d.text(((size - f.getlength("K")) / 2, size * 0.02), "K", font=f, fill=BASE)
    return img
LOGO = k_logo(96); LOGO_BIG = k_logo(200)
LINK = "twitch.tv/videos/2268401193"
CLIPS = [("The getaway that should not have worked", "3:41:08 to 3:41:48"), ("Chat calls it, streamer loses it", "3:42:02 to 3:42:29"),
         ("Six hours in and still swerving", "5:12:40 to 5:13:05")]

def klipit_scene(base, t):
    d = ImageDraw.Draw(base)
    a0 = ease((t - 19.6) / 0.5)
    panel = Image.new("RGBA", (980, 1240), (0, 0, 0, 0)); pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((0, 0, 979, 1239), 48, fill=(18, 18, 28, 250), outline=(34, 211, 238, 110), width=3)
    panel.alpha_composite(LOGO, (50, 46))
    pd.text((170, 52), "Klipit", font=f_uiB, fill=WHITE)
    pd.text((170, 106), "GTA 6 stream clipper", font=f_uiS, fill=MUTED)
    # input
    pd.rounded_rectangle((50, 200, 930, 310), 24, fill=(10, 10, 15, 255), outline=(60, 64, 82, 255), width=2)
    nch = int(clamp((t - 20.0) / 1.0) * len(LINK)); typed = LINK[:nch]
    pd.text((84, 234), typed, font=f_monoS, fill=WHITE)
    if (t * 2) % 1 < 0.6 and nch < len(LINK): pd.rectangle((86 + f_monoS.getlength(typed), 232, 90 + f_monoS.getlength(typed), 276), fill=CYAN)
    # button
    pressed = t > 21.2
    pd.rounded_rectangle((50, 340, 930, 450), 24, fill=CYAN if not pressed else (20, 160, 185))
    s = "Clip it"; pd.text(((980 - f_uiB.getlength(s)) / 2, 368), s, font=f_uiB, fill=BASE)
    # progress
    if t > 21.3:
        p = clamp((t - 21.3) / 1.4)
        lab = "Scanning 6:42:17 of stream" if p < 1 else "Clips ready"
        pd.text((50, 490), lab, font=f_uiS, fill=CYAN if p >= 1 else MUTED)
        pd.rounded_rectangle((50, 540, 930, 556), 8, fill=(40, 44, 60))
        pd.rounded_rectangle((50, 540, 50 + 880 * p, 556), 8, fill=CYAN)
    for i, (title, rng_) in enumerate(CLIPS):
        ts = 22.8 + i * 0.35
        if t < ts: continue
        ca = ease((t - ts) / 0.35)
        card = Image.new("RGBA", (880, 180), (0, 0, 0, 0)); cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 879, 179), 26, fill=(28, 28, 42, 255))
        th = game_view(3.8 + i * 2, 0.9 if i < 2 else 0.2).crop((240, 300, 840, 1060)).resize((118, 150), Image.BILINEAR)
        m = Image.new("L", th.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, 117, 149), 16, fill=255); th.putalpha(m)
        card.alpha_composite(th, (16, 15))
        cd.text((160, 26), title, font=f_uiS, fill=WHITE)
        cd.text((160, 76), rng_, font=f_monoS, fill=MUTED)
        cd.rounded_rectangle((160, 122, 296, 160), 10, fill=(34, 211, 238, 40)); cd.text((176, 124), "Vertical", font=f_uiS, fill=CYAN)
        cd.rounded_rectangle((680, 112, 860, 164), 14, fill=CYAN); cd.text((706, 118), "Download", font=f_uiS, fill=BASE)
        paste_alpha(panel, card, ca, (50, 600 + i * 200 + (1 - ca) * 30))
    paste_alpha(base, panel, a0, (50, 330 + (1 - a0) * 40))

def make_qr(url, box=420):
    import segno
    buf = io.BytesIO(); segno.make(url, error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
    pad = 30; code = Image.open(buf).convert("RGBA").resize((box - pad * 2, box - pad * 2), Image.NEAREST)
    card = Image.new("RGBA", (box, box), (0, 0, 0, 0)); ImageDraw.Draw(card).rounded_rectangle((0, 0, box - 1, box - 1), 36, fill=(255, 255, 255, 255))
    card.alpha_composite(code, (pad, pad))
    lg = k_logo(92); bg = Image.new("RGBA", (112, 112), (0, 0, 0, 0)); ImageDraw.Draw(bg).rounded_rectangle((0, 0, 111, 111), 26, fill=(255, 255, 255, 255))
    bg.alpha_composite(lg, (10, 10)); card.alpha_composite(bg, ((box - 112) // 2, (box - 112) // 2))
    halo = Image.new("RGBA", (box + 120, box + 120), (0, 0, 0, 0)); hm = Image.new("L", halo.size, 0)
    ImageDraw.Draw(hm).rounded_rectangle((60, 60, box + 59, box + 59), 36, fill=255)
    hc = Image.new("RGBA", halo.size, CYAN + (0,)); hc.putalpha(hm.filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * 0.6)))
    halo.alpha_composite(hc); halo.alpha_composite(card, (60, 60))
    return halo
QR = make_qr(SITE)
WM = glow_text("KLIPIT", f_huge, WHITE, blur=26, strength=0.8, glow=CYAN)
T_GTA = glow_text("GTA 6 IS ALMOST HERE.", f_capS, YEL, blur=12, strength=0.6)

def end_card(base, t):
    a = ease((t - 25.0) / 0.6)
    paste_alpha(base, LOGO_BIG, a, ((W - 200) // 2, 150 + (1 - a) * 30))
    paste_alpha(base, WM, ease((t - 25.2) / 0.6), ((W - WM.width) // 2, 340))
    paste_alpha(base, T_GTA, ease((t - 25.5) / 0.5), ((W - T_GTA.width) // 2, 640))
    caption(base, t, 25.7, 31, "Paste the stream. Post the clips.", 730, f_capS, WHITE)
    qa = ease((t - 26.0) / 0.5)
    paste_alpha(base, QR, qa, ((W - QR.width) // 2, 860 + (1 - qa) * 30))
    caption(base, t, 26.3, 31, "SCAN TO SUBSCRIBE", 1415, f_cap, CYAN)
    caption(base, t, 26.7, 31, "Plans from $20 a month  ·  Cancel anytime", 1530, f_lab, WHITE)
    caption(base, t, 27.0, 31, "klipit.onrender.com  ·  link in bio", 1600, f_monoS, MUTED)
    caption(base, t, 27.3, 31, "HSW365 Media  ·  Turn Negative Into Positive", 1760, f_monoS, (100, 104, 125))

# ---------- timeline ----------
def frame(i):
    t = i / FPS
    base = Image.new("RGBA", (W, H), BASE + (255,))
    if t < 9.0:  # live stream at 3am
        heat = clamp((t - 3.4) / 0.6) * (1 - clamp((t - 8.0) / 1.0))
        shake = 7 * heat if 3.6 < t < 7.8 else 0
        base.alpha_composite(game_view(t, heat, shake=shake), (0, 0))
        hud = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        live_hud(hud, t, 6 * 3600 + 41 * 60 + 48 + t, int(212 + heat * 40 + t * 3), ended=t > 8.6)
        chat_panel(hud, t, GH); base.alpha_composite(hud)
        caption(base, t, 0.4, 3.2, "3:12 AM. Six hours live.", 380, f_cap)
        caption(base, t, 1.3, 3.2, "212 people watching.", 480, f_capS, MUTED)
        if 3.6 < t < 3.75: base.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(220 * (1 - (t - 3.6) / 0.15)))))
        caption(base, t, 4.2, 7.6, "The run of his life.", 300, f_big, YEL)
        caption(base, t, 6.0, 8.6, "\"Yo... somebody clip that.\"", 470, f_cap, WHITE)
        if t > 8.6:
            k = ease((t - 8.6) / 0.4); base.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * k))))
    elif t < 10.6:  # stream ends
        caption(base, t, 9.0, 10.5, "Nobody did.", 860, f_big, (239, 68, 68))
    elif t < 17.0:  # morning: lost in the VOD
        vod_scene(base, t)
        caption(base, t, 10.7, 13.0, "Next morning.", 90, f_capS, MUTED)
        caption(base, t, 12.6, 16.8, "\"It was hour three... or five?\"", 1680, f_capS, WHITE)
        if t > 15.4: notification(base, t, 15.4)
    elif t < 19.4:  # gut punch
        vod_scene(base, 16.9)
        base.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(200 * ease((t - 17.0) / 0.4)))))
        notification(base, t, 15.4)
        caption(base, t, 17.2, 19.4, "His moment.", 760, f_big, WHITE)
        caption(base, t, 17.8, 19.4, "Somebody else's views.", 900, f_cap, (239, 68, 68))
    elif t < 25.0:  # next stream: Klipit
        caption(base, t, 19.4, 24.9, "Next stream, he pasted the link.", 140, f_capS, CYAN)
        klipit_scene(base, t)
        caption(base, t, 23.9, 24.9, "Every moment. Clipped.", 1620, f_cap, WHITE)
    else:
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(bg)
        for k in range(0, H, 60): gd.line([(0, k), (W, k)], fill=(34, 211, 238, 14))
        base.alpha_composite(bg)
        end_card(base, t)
    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < 0.4: arr *= ease(t / 0.4)
    if t > 29.4: arr *= clamp((30 - t) / 0.6)
    return np.clip(arr * VIG + GRAIN[i % 6], 0, 255).astype(np.uint8)

# ---------- audio: original score, synthesized ----------
def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr; a = np.zeros(n)
    def env_at(t0, dur):
        i0 = int(t0 * sr); m = max(0, min(n - i0, int(dur * sr))); return i0, m, np.arange(m) / sr
    def kick(t0, amp=0.9):
        i0, m, x = env_at(t0, 0.35); f = 55 + 90 * np.exp(-x * 30)
        a[i0:i0 + m] += amp * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-x * 9)
    def hat(t0, amp=0.12):
        i0, m, x = env_at(t0, 0.06); a[i0:i0 + m] += amp * np.random.default_rng(int(t0 * 1000)).normal(0, 1, m) * np.exp(-x * 70)
    def snare(t0, amp=0.35):
        i0, m, x = env_at(t0, 0.25); r = np.random.default_rng(int(t0 * 999)).normal(0, 1, m)
        a[i0:i0 + m] += amp * (r * np.exp(-x * 18) + 0.5 * np.sin(2 * np.pi * 190 * x) * np.exp(-x * 25))
    def bass(t0, f, dur, amp=0.32):
        i0, m, x = env_at(t0, dur); s = np.sign(np.sin(2 * np.pi * f * x)) * 0.5 + np.sin(2 * np.pi * f * x)
        a[i0:i0 + m] += amp * s * np.clip(x / 0.01, 0, 1) * np.exp(-x * 2.5)
    def pad(t0, t1, freqs, amp):
        i0, m, x = env_at(t0, t1 - t0)
        s = sum(np.sin(2 * np.pi * f * x + k) for k, f in enumerate(freqs)) / len(freqs)
        e = np.clip(x / 0.6, 0, 1) * np.clip(((t1 - t0) - x) / 0.5, 0, 1); a[i0:i0 + m] += amp * s * e
    def blip(t0, f, amp=0.08, d=0.08):
        i0, m, x = env_at(t0, d); a[i0:i0 + m] += amp * np.sin(2 * np.pi * f * x) * np.exp(-x * 40)
    bpm = 140; beat = 60 / bpm
    # cold open: low pad + soft hats
    pad(0, 3.6, (55, 82.4, 110), 0.10)
    for k in range(int(3.6 / (beat / 2))): hat(k * beat / 2, 0.05)
    # hype: full beat 3.6 -> 8.4
    t0 = 3.6; notes = [55, 55, 65.4, 49]
    k = 0
    while t0 < 8.4:
        kick(t0); hat(t0 + beat / 2)
        if k % 2: snare(t0)
        bass(t0, notes[(k // 2) % 4], beat * 0.9)
        k += 1; t0 += beat
    i0 = int(3.6 * sr); m = int(1.2 * sr); x = np.arange(m) / sr  # siren riser
    a[i0:i0 + m] += 0.12 * np.sin(2 * np.pi * (600 + 300 * np.sin(2 * np.pi * 2 * x)) * x) * np.clip(1 - x / 1.2, 0, 1)
    # silence hit at 8.6, then heartbeat while he searches
    kick(8.6, 1.0)
    for hb in np.arange(10.8, 17.0, 0.85): kick(hb, 0.35); kick(hb + 0.22, 0.22)
    for ts, _ in SCRUB: blip(ts, 1800, 0.07, 0.05)
    pad(10.6, 17.0, (73.4, 110, 146.8), 0.06)
    # notification + gut punch
    blip(15.4, 1318.5, 0.12, 0.4); blip(15.55, 987.8, 0.1, 0.5)
    pad(17.0, 19.4, (46.2, 69.3, 92.5), 0.14); kick(17.0, 1.0)
    # Klipit: typing clicks, then the drop
    for c in np.arange(20.0, 21.0, 1.0 / len(LINK) * 1.0): blip(c, 2400, 0.04, 0.02)
    blip(21.2, 880, 0.15, 0.2)
    t0 = 21.3; k = 0
    while t0 < 29.0:
        kick(t0, 0.85); hat(t0 + beat / 2, 0.1); hat(t0 + beat / 4, 0.05)
        if k % 2: snare(t0, 0.3)
        bass(t0, [55, 65.4, 73.4, 61.7][(k // 4) % 4], beat * 0.9, 0.28)
        k += 1; t0 += beat
    for i, _ in enumerate(CLIPS): blip(22.8 + i * 0.35, 1567.98, 0.1, 0.15)
    pad(25.0, 30.0, (110, 164.8, 220, 277.2), 0.09)
    a *= np.clip((DUR - tt) / 0.8, 0, 1)
    a = np.tanh(a * 1.3); a = a / max(1e-6, np.max(np.abs(a))) * 0.85
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    out = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "preview":
        for ts in [float(x) for x in sys.argv[3].split(",")]:
            Image.fromarray(frame(int(ts * FPS))).save(f"{out}_{ts:.1f}.png")
        sys.exit()
    wav = os.path.join(tempfile.mkdtemp(prefix="klipit-"), "a.wav"); audio(wav)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-b:v", "7M", "-maxrate", "8M", "-bufsize", "16M",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i in range(N): p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait(); print("done", out)
