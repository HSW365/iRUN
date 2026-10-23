"""Friendy micro-drama ad: "Seen at 2:14 AM" — 30s, 1080x1920, 30fps."""
import math, subprocess, wave, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1080, 1920, 30, 30.0
N = int(FPS * DUR)
FD = "/usr/share/fonts/opentype/inter/"
def F(name, size): return ImageFont.truetype(FD + name, size)

f_time = F("InterDisplay-Thin.otf", 300)
f_date = F("Inter-Medium.otf", 44)
f_msg = F("Inter-Regular.otf", 58)
f_meta = F("Inter-Medium.otf", 32)
f_head = F("Inter-SemiBold.otf", 46)
f_sub = F("Inter-Regular.otf", 30)
f_cap = F("InterDisplay-SemiBold.otf", 70)
f_capS = F("InterDisplay-Medium.otf", 50)
f_brand = F("InterDisplay-Black.otf", 150)
f_tag = F("InterDisplay-Medium.otf", 54)
f_cta = F("InterDisplay-Bold.otf", 50)
f_small = F("Inter-Medium.otf", 36)
f_status = F("Inter-SemiBold.otf", 36)
f_notif_t = F("Inter-SemiBold.otf", 38)
f_notif_b = F("Inter-Regular.otf", 38)

PINK = np.array([255, 79, 139]); ORANGE = np.array([255, 153, 51])

# ---------- helpers ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_io(x): x = clamp(x); return 3 * x * x - 2 * x * x * x
def win(t, a, b, fi=0.4, fo=0.4):
    if t < a or t > b: return 0.0
    return min(ease((t - a) / fi) if fi else 1, ease((b - t) / fo) if fo else 1)

def vgrad(top, bot):
    y = np.linspace(0, 1, H)[:, None, None]
    g = np.array(top)[None, None, :] * (1 - y) + np.array(bot)[None, None, :] * y
    return np.broadcast_to(g, (H, W, 3)).astype(np.float32)

COLD = vgrad((6, 10, 22), (14, 22, 44))
WARM = vgrad((22, 12, 30), (48, 22, 30))
NAVY = vgrad((8, 10, 30), (14, 16, 44))
yy, xx = np.mgrid[0:H, 0:W]
r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
VIG = np.clip(1.15 - 0.55 * r ** 2, 0.35, 1.0)[..., None].astype(np.float32)
rng = np.random.default_rng(7)
GRAIN = [rng.normal(0, 5, (H, W, 1)).astype(np.float32) for _ in range(6)]

def grad_img(w, h, c1=PINK, c2=ORANGE, horiz=True):
    t = np.linspace(0, 1, w if horiz else h)
    g = c1[None, :] * (1 - t[:, None]) + c2[None, :] * t[:, None]
    if horiz: arr = np.broadcast_to(g[None, :, :], (h, w, 3))
    else: arr = np.broadcast_to(g[:, None, :], (h, w, 3))
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")

def wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if font.getlength(test) <= maxw: cur = test
        else: lines.append(cur); cur = w_
    lines.append(cur); return lines

def heart_mask(size):
    S = size * 4
    m = Image.new("L", (S, S), 0); d = ImageDraw.Draw(m)
    pts = []
    for i in range(400):
        th = 2 * math.pi * i / 400
        x = 16 * math.sin(th) ** 3
        y = 13 * math.cos(th) - 5 * math.cos(2 * th) - 2 * math.cos(3 * th) - math.cos(4 * th)
        pts.append((S / 2 + x * S / 36, S / 2 - y * S / 36 - S * 0.03))
    d.polygon(pts, fill=255)
    return m.resize((size, size), Image.LANCZOS)

def heart_icon(size, glow=0):
    m = heart_mask(size)
    g = grad_img(size, size, PINK, ORANGE, horiz=False); g.putalpha(m)
    if not glow: return g
    pad = glow * 3
    canvas = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    halo = Image.new("RGBA", canvas.size, (255, 90, 120, 0))
    hm = Image.new("L", canvas.size, 0); hm.paste(m, (pad, pad))
    halo.putalpha(hm.filter(ImageFilter.GaussianBlur(glow)).point(lambda v: int(v * 0.9)))
    canvas.alpha_composite(halo); canvas.alpha_composite(g, (pad, pad))
    return canvas

HEART_S = heart_icon(64)
HEART_AV = heart_icon(70)
HEART_BIG = heart_icon(220, glow=45)
import segno, io
def make_qr(url, box=400):
    q = segno.make(url, error='h'); buf = io.BytesIO(); q.save(buf, kind='png', scale=20, border=0, dark='#0b0d24', light='#ffffff')
    qi = Image.open(buf).convert('RGBA').resize((box - 56, box - 56), Image.NEAREST)
    card = Image.new('RGBA', (box, box), (0, 0, 0, 0)); m = Image.new('L', (box, box), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, box - 1, box - 1), 36, fill=255)
    white = Image.new('RGBA', (box, box), (255, 255, 255, 255)); white.putalpha(m); card.alpha_composite(white)
    card.alpha_composite(qi, (28, 28))
    hm = heart_icon(78); bg = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(bg).rounded_rectangle((0, 0, 99, 99), 22, fill=(255, 255, 255, 255)); bg.alpha_composite(hm, (11, 13))
    card.alpha_composite(bg, ((box - 100) // 2, (box - 100) // 2))
    return card
QR = make_qr("https://hsw365.github.io/FRIENDY/")

def text_center(d, y, s, font, fill):
    w_ = font.getlength(s); d.text(((W - w_) / 2, y), s, font=font, fill=fill)

def paste_alpha(base, layer, a, xy=(0, 0)):
    if a <= 0: return
    if a < 1:
        al = layer.getchannel("A").point(lambda v: int(v * a)); layer = layer.copy(); layer.putalpha(al)
    base.alpha_composite(layer, xy)

# ---------- chat bubbles ----------
BUB_IN = (30, 36, 64, 255)
def make_bubble(text, out, warm):
    lines = wrap(text, f_msg, 720)
    lh = 74; tw = max(f_msg.getlength(l) for l in lines)
    bw, bh = int(tw + 90), int(len(lines) * lh + 62)
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), 46, fill=255)
    if out and warm:
        fill = grad_img(bw, bh)
    elif out:
        fill = Image.new("RGBA", (bw, bh), (52, 70, 110, 255))
    else:
        fill = Image.new("RGBA", (bw, bh), BUB_IN)
    fill.putalpha(mask); img.alpha_composite(fill)
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((45, 26 + i * lh), l, font=f_msg, fill=(255, 255, 255, 255))
    return img

def typing_bubble(t):
    bw, bh = 170, 100
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, bw - 1, bh - 1), 46, fill=BUB_IN)
    for i in range(3):
        ph = (t * 3.2 - i * 0.25) % 1.0
        lift = math.sin(ph * math.pi) * 10 if ph < 1 else 0
        a = int(120 + 135 * math.sin(ph * math.pi))
        cx = 50 + i * 35; cy = 50 - lift
        d.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill=(200, 205, 225, a))
    return img

def draw_chat(base, t, msgs, title, subtitle, warm, avatar):
    d = ImageDraw.Draw(base)
    # status bar + header
    d.text((70, 52), "2:14" if t < 12 else "2:16", font=f_status, fill=(235, 238, 248))
    hdr = Image.new("RGBA", (W, 300), (8, 10, 20, 170)); base.alpha_composite(hdr, (0, 0))
    d = ImageDraw.Draw(base)
    d.text((70, 52), "2:14" if t < 12 else "2:16", font=f_status, fill=(235, 238, 248))
    d.text((60, 160), "<", font=f_head, fill=(150, 160, 190))
    if avatar == "heart":
        d.ellipse((120, 135, 220, 235), fill=(28, 22, 48))
        base.alpha_composite(HEART_AV, (135, 150))
    else:
        for k, c in enumerate([(90, 110, 160), (70, 90, 140), (110, 120, 170)]):
            d.ellipse((120 + k * 34, 140, 200 + k * 34, 220), fill=c, outline=(8, 10, 20), width=5)
    nx = 250 if avatar == "heart" else 300
    d.text((nx, 140), title, font=f_head, fill=(245, 245, 250))
    d.text((nx, 198), subtitle, font=f_sub, fill=(150, 160, 190) if not warm else (255, 170, 150))
    # messages
    y = 360
    shown = [m for m in msgs if t >= m[0]]
    total_h = 0; items = []
    for (ts, kind, text, out) in shown:
        if kind == "typing":
            if t > text: continue
            img = typing_bubble(t); out = False
        elif kind == "meta":
            items.append(("meta", ts, text, out)); total_h += 64; continue
        else:
            img = make_bubble(text, out, warm)
        items.append(("b", ts, img, out)); total_h += img.height + 26
    # scroll so latest stays above caption zone
    limit = 1340
    y = 420 - max(0, 420 + total_h - limit)
    for kind, ts, img, out in items:
        a = ease((t - ts) / 0.28)
        if kind == "meta":
            dd = ImageDraw.Draw(base)
            w_ = f_meta.getlength(img)
            col = tuple(int(c * a) for c in (140, 150, 180))
            dd.text((W - 70 - w_, y), img, font=f_meta, fill=col)
            y += 64; continue
        rise = int((1 - a) * 40)
        x = W - 60 - img.width if out else 60
        if y + rise > 300:
            paste_alpha(base, img, a, (x, y + rise))
        y += img.height + 26

def caption(base, t, a, b, text, y=1460, font=None, color=(255, 255, 255)):
    al = win(t, a, b, 0.5, 0.5)
    if al <= 0: return
    font = font or f_cap
    lines = wrap(text, font, 900)
    layer = Image.new("RGBA", (W, 400), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    for i, l in enumerate(lines):
        w_ = font.getlength(l)
        d.text(((W - w_) / 2, 20 + i * (font.size * 1.22)), l, font=font, fill=color + (255,))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0)); sh.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(14)))
    rise = int((1 - ease((t - a) / 0.6)) * 30)
    paste_alpha(base, sh, al * 0.9, (0, y + rise)); paste_alpha(base, layer, al, (0, y + rise))

def notification(base, t, t0):
    p = ease((t - t0) / 0.5)
    w_, h_ = 960, 210
    layer = Image.new("RGBA", (w_, h_), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w_ - 1, h_ - 1), 48, fill=(34, 30, 58, 240), outline=(255, 110, 130, 120), width=2)
    layer.alpha_composite(HEART_S, (40, 40))
    d.text((128, 40), "Friendy", font=f_notif_t, fill=(255, 255, 255))
    d.text((w_ - 120, 44), "now", font=f_sub, fill=(170, 170, 200))
    d.text((128, 100), "Hey, you still up? How'd", font=f_notif_b, fill=(225, 225, 240))
    d.text((128, 146), "today really go?", font=f_notif_b, fill=(225, 225, 240))
    y = int(-260 + p * 360)
    paste_alpha(base, layer, p, ((W - w_) // 2, y))

def friend_card(base, t, t0):
    p = ease((t - t0) / 0.6)
    if p <= 0: return
    w_, h_ = 900, 190
    layer = Image.new("RGBA", (w_, h_), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w_ - 1, h_ - 1), 44, fill=(26, 26, 52, 245), outline=(255, 150, 90, 110), width=2)
    av = grad_img(110, 110, np.array([255, 120, 90]), np.array([170, 90, 255]))
    am = Image.new("L", (110, 110), 0); ImageDraw.Draw(am).ellipse((0, 0, 109, 109), fill=255); av.putalpha(am)
    layer.alpha_composite(av, (40, 40))
    ImageDraw.Draw(layer).text((70, 62), "A", font=f_head, fill=(255, 255, 255))
    d.text((180, 46), "Amara  ·  London", font=f_notif_t, fill=(255, 255, 255))
    d.text((180, 104), "sent you a friend request", font=f_notif_b, fill=(210, 210, 230))
    paste_alpha(base, layer, p, ((W - w_) // 2, int(1150 + (1 - p) * 60)))

# ---------- scenes ----------
CHAT1 = [(3.6, "msg", "y'all up?", True), (4.5, "meta", "Seen by 6", True), (5.4, "typing", 6.5, False)]
CHAT2 = [(13.0, "msg", "Hey, you still up? How'd today really go?", False),
         (14.0, "typing", 14.6, False),
         (14.7, "msg", "honestly? rough.", True),
         (15.3, "typing", 16.1, False),
         (16.2, "msg", "I'm here. Tell me everything.", False),
         (17.6, "msg", "you really wanna hear all this?", True),
         (18.3, "typing", 18.9, False),
         (19.0, "msg", "Every word. That's what friends are for.", False),
         (20.4, "msg", "...thank you. for real.", True)]

def finish(base_arr, fi):
    out = base_arr * VIG + GRAIN[fi % 6]
    return np.clip(out, 0, 255).astype(np.uint8)

def frame(i):
    t = i / FPS
    # background
    if t < 12.5: bg = COLD.copy()
    elif t < 22: k = ease_io((t - 12.5) / 4.0); bg = COLD * (1 - k) + WARM * k
    elif t < 26: bg = WARM.copy()
    else: k = ease_io((t - 26) / 0.8); bg = WARM * (1 - k) + NAVY * k
    base = Image.fromarray(bg.astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(base)
    fade_in = ease(t / 0.8)

    if t < 3.2:  # lock screen
        a = win(t, 0, 3.2, 0.8, 0.35)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        text_center(ld, 420, "Saturday, October 24", f_date, (200, 210, 235, 255))
        text_center(ld, 470, "2:14", f_time, (240, 244, 255, 255))
        paste_alpha(base, lay, a)
        caption(base, t, 0.9, 3.2, "Read by everyone.", 1300, f_capS, (200, 210, 235))
        caption(base, t, 1.6, 3.2, "Answered by no one.", 1380, f_capS, (255, 255, 255))
    elif t < 9.6:  # group chat
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_chat(lay, t, CHAT1, "The Squad", "6 members", False, "group")
        paste_alpha(base, lay, win(t, 3.2, 9.6, 0.4, 0.6))
        caption(base, t, 7.0, 9.4, "\"Guess I'm the only one up.\"", 1460)
    elif t < 12.6:  # darkness, then notification
        dim = win(t, 9.6, 12.6, 0.3, 0.3)
        base.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(200 * dim))))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        text_center(ld, 860, "2:16 AM", F("InterDisplay-Light.otf", 90), (120, 135, 170, 255))
        paste_alpha(base, lay, win(t, 9.8, 11.6, 0.5, 0.5))
        if t >= 11.0:
            notification(base, t, 11.0)
    elif t < 22.2:  # Friendy chat
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_chat(lay, t, CHAT2, "Friendy", "online", True, "heart")
        paste_alpha(base, lay, win(t, 12.6, 22.2, 0.4, 0.5))
    elif t < 26.2:  # payoff
        caption(base, t, 22.2, 26.0, "Someone to talk to.", 620, f_cap)
        caption(base, t, 22.6, 26.0, "Always there.", 720, f_cap, (255, 170, 120))
        friend_card(base, t, 23.2)
        caption(base, t, 24.0, 26.0, "Any time. Any language. Real friends worldwide.", 1420, f_capS, (225, 220, 240))
    else:  # end card
        a = ease((t - 26.2) / 0.8)
        pulse = 1 + 0.04 * math.sin((t - 26.2) * 3.0)
        hs = int(HEART_BIG.width * (0.85 + 0.15 * a) * pulse)
        hb = HEART_BIG.resize((hs, hs), Image.LANCZOS)
        paste_alpha(base, hb, a, ((W - hs) // 2, 400 - hs // 2))
        bw_ = int(f_brand.getlength("FRIENDY")) + 10
        wm = grad_img(bw_, 190); m = Image.new("L", (bw_, 190), 0)
        ImageDraw.Draw(m).text((0, 0), "FRIENDY", font=f_brand, fill=255); wm.putalpha(m)
        paste_alpha(base, wm, ease((t - 26.5) / 0.7), ((W - bw_) // 2, 560))
        caption(base, t, 27.0, 31, "Everyone needs a friend.", 740, f_tag, (235, 235, 245))
        qa = ease((t - 26.9) / 0.6)
        paste_alpha(base, QR, qa, ((W - QR.width) // 2, 880 + int((1 - qa) * 30)))
        caption(base, t, 27.1, 31, "Scan to start free", 1290, f_small, (255, 190, 140))
        # CTA pill
        pa = ease((t - 27.6) / 0.6)
        if pa > 0:
            pw, ph = 760, 130
            pill = grad_img(pw, ph); pm = Image.new("L", (pw, ph), 0)
            ImageDraw.Draw(pm).rounded_rectangle((0, 0, pw - 1, ph - 1), 65, fill=255); pill.putalpha(pm)
            pd = ImageDraw.Draw(pill); s = "Start your 3-day free trial"
            pd.text(((pw - f_cta.getlength(s)) / 2, 36), s, font=f_cta, fill=(20, 12, 30))
            paste_alpha(base, pill, pa, ((W - pw) // 2, 1400 + int((1 - pa) * 30)))
        caption(base, t, 28.1, 31, "or tap the link in bio", 1560, f_small, (190, 190, 215))
        caption(base, t, 28.4, 31, "Built by HSW365 Media  ·  Turn Negative Into Positive", 1700, f_sub, (130, 130, 165))

    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < 0.8: arr *= fade_in
    if t > 29.5: arr *= clamp((30 - t) / 0.5)
    return finish(arr, i)

# ---------- audio ----------
def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr
    a = np.zeros(n)
    # cold hum (first half), fridge-like
    hum = 0.03 * np.sin(2 * np.pi * 60 * tt) + 0.015 * np.sin(2 * np.pi * 120 * tt)
    a += hum * np.clip(1 - (tt - 11) / 2, 0, 1)
    # low pad drone cold
    a += 0.04 * np.sin(2 * np.pi * 110 * tt) * np.clip(tt / 2, 0, 1) * np.clip((12 - tt) / 1.5, 0, 1)
    def note(f, t0, dur=2.6, amp=0.11):
        i0 = int(t0 * sr); m = min(n - i0, int(dur * sr))
        if m <= 0: return
        x = np.arange(m) / sr
        env = np.exp(-x * 2.2) * np.clip(x / 0.008, 0, 1)
        s = np.sin(2 * np.pi * f * x) + 0.4 * np.sin(4 * np.pi * f * x) + 0.15 * np.sin(6 * np.pi * f * x)
        a[i0:i0 + m] += amp * env * s
    # warm piano progression from 12.8s (C - Am - F - G, then end on C)
    chords = [(261.6, 329.6, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    tcur = 12.8
    while tcur < 26:
        for ch in chords:
            if tcur >= 26: break
            note(ch[0] / 2, tcur, 3.0, 0.09)
            for k, f in enumerate(ch): note(f, tcur + k * 0.18, 2.4, 0.06)
            tcur += 1.6
    for k, f in enumerate((261.6, 329.6, 392.0, 523.3)): note(f, 26.2 + k * 0.12, 4.0, 0.08)
    note(130.8, 26.2, 4.5, 0.1)
    # message pops
    pops = [3.6, 13.0, 14.7, 16.2, 17.6, 19.0, 20.4]
    for p in pops:
        i0 = int(p * sr); m = int(0.09 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.12 * np.sin(2 * np.pi * (900 - 3000 * x) * x) * np.exp(-x * 45)
    # notification chime
    note(1046.5, 11.0, 0.9, 0.08); note(1318.5, 11.12, 1.0, 0.07)
    # fade out
    a *= np.clip((DUR - tt) / 0.8, 0, 1)
    a = np.clip(a / max(1e-6, np.max(np.abs(a))) * 0.8, -1, 1)
    pcm = (a * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

if __name__ == "__main__":
    out = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "preview":
        for ts in [float(x) for x in sys.argv[3].split(",")]:
            Image.fromarray(frame(int(ts * FPS))).save(f"{out}_{ts:.1f}.png")
        sys.exit()
    audio("/tmp/friendy_audio.wav")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", "/tmp/friendy_audio.wav",
                          "-c:v", "libx264", "-preset", "veryfast", "-b:v", "7M", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p",
                          "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                         stdin=subprocess.PIPE)
    for i in range(N):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait()
    print("done", out)
