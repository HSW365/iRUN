"""New Ark micro-drama ad: "No Heat at 11 PM" — 30s, 1080x1920, 30fps."""
import io, math, subprocess, sys, wave
import numpy as np
import segno
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1080, 1920, 30, 30.0
N = int(FPS * DUR)
FD = "/usr/share/fonts/opentype/inter/"
def F(n, s): return ImageFont.truetype(FD + n, s)
f_time = F("InterDisplay-Thin.otf", 250); f_date = F("Inter-Medium.otf", 44)
f_msg = F("Inter-Regular.otf", 56); f_meta = F("Inter-Medium.otf", 32)
f_head = F("Inter-SemiBold.otf", 46); f_sub = F("Inter-Regular.otf", 30)
f_cap = F("InterDisplay-SemiBold.otf", 70); f_capS = F("InterDisplay-Medium.otf", 50)
f_big = F("InterDisplay-Black.otf", 112); f_mid = F("InterDisplay-Bold.otf", 50)
f_small = F("Inter-Medium.otf", 36); f_stat = F("Inter-SemiBold.otf", 36)
f_temp = F("InterDisplay-ExtraLight.otf", 300); f_url = F("InterDisplay-Bold.otf", 64)

AMBER = np.array([255, 150, 50]); EMBER = np.array([255, 95, 40])
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_io(x): x = clamp(x); return 3 * x * x - 2 * x ** 3
def win(t, a, b, fi=0.4, fo=0.4):
    if t < a or t > b: return 0.0
    return min(ease((t - a) / fi) if fi else 1, ease((b - t) / fo) if fo else 1)

def vgrad(top, bot):
    y = np.linspace(0, 1, H)[:, None, None]
    return np.broadcast_to(np.array(top) * (1 - y) + np.array(bot) * y, (H, W, 3)).astype(np.float32)
COLD = vgrad((4, 10, 22), (10, 24, 44)); NAVY = vgrad((6, 24, 43), (4, 14, 28)); WARM = vgrad((26, 16, 14), (52, 28, 16))
yy, xx = np.mgrid[0:H, 0:W]
r = np.sqrt(((xx - W / 2) / (W * .75)) ** 2 + ((yy - H / 2) / (H * .7)) ** 2)
VIG = np.clip(1.15 - .55 * r ** 2, .35, 1)[..., None].astype(np.float32)
rng = np.random.default_rng(3); GRAIN = [rng.normal(0, 5, (H, W, 1)).astype(np.float32) for _ in range(6)]

def grad_img(w, h, c1=AMBER, c2=EMBER):
    t = np.linspace(0, 1, w); g = c1[None] * (1 - t[:, None]) + c2[None] * t[:, None]
    return Image.fromarray(np.broadcast_to(g[None], (h, w, 3)).astype(np.uint8)).convert("RGBA")
def wrap(text, font, maxw):
    out, cur = [], ""
    for w_ in text.split():
        t = (cur + " " + w_).strip()
        if font.getlength(t) <= maxw: cur = t
        else: out.append(cur); cur = w_
    return out + [cur]
def paste(base, layer, a, xy=(0, 0)):
    if a <= 0: return
    if a < 1:
        layer = layer.copy(); layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
    base.alpha_composite(layer, xy)
def center(d, y, s, f, fill): d.text(((W - f.getlength(s)) / 2, y), s, font=f, fill=fill)
def caption(base, t, a, b, text, y, font=None, color=(255, 255, 255)):
    al = win(t, a, b, .5, .5)
    if al <= 0: return
    font = font or f_cap
    lay = Image.new("RGBA", (W, 420), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for i, l in enumerate(wrap(text, font, 920)):
        d.text(((W - font.getlength(l)) / 2, 20 + i * font.size * 1.22), l, font=font, fill=color + (255,))
    sh = Image.new("RGBA", lay.size, (0, 0, 0, 0)); sh.putalpha(lay.getchannel("A").filter(ImageFilter.GaussianBlur(14)))
    rise = int((1 - ease((t - a) / .6)) * 30)
    paste(base, sh, al * .9, (0, y + rise)); paste(base, lay, al, (0, y + rise))

def logo(size):
    """New Ark mark: a house roofline with a flame inside."""
    S = size * 4; m = Image.new("L", (S, S), 0); d = ImageDraw.Draw(m)
    lw = int(S * .07)
    d.line([(S * .12, S * .5), (S * .5, S * .14), (S * .88, S * .5)], fill=255, width=lw, joint="curve")
    d.line([(S * .22, S * .42), (S * .22, S * .86), (S * .78, S * .86), (S * .78, S * .42)], fill=255, width=lw, joint="curve")
    pts = []
    for i in range(200):
        th = 2 * math.pi * i / 200
        x = .5 + .13 * math.sin(th) * (1 - .55 * (1 - math.cos(th)) / 2) ** .5
        y = .66 - .2 * (math.cos(th) * .5 + .5) ** 1.6 + .08 * (1 - math.cos(th)) * .0
        pts.append((S * x, S * (.78 - .32 * ((math.cos(th) + 1) / 2) ** 1.4) if math.cos(th) > -1 else S * .78))
    d.polygon([(S * .5, S * .44), (S * .62, S * .64), (S * .6, S * .76), (S * .5, S * .8), (S * .4, S * .76), (S * .38, S * .64)], fill=255)
    m = m.resize((size, size), Image.LANCZOS)
    g = grad_img(size, size); g.putalpha(m); return g
LOGO_S = logo(70); LOGO_B = logo(220)

def make_qr(url, box=380):
    buf = io.BytesIO(); segno.make(url, error="h").save(buf, kind="png", scale=20, border=0, dark="#06182b", light="#ffffff")
    qi = Image.open(buf).convert("RGBA").resize((box - 52, box - 52), Image.NEAREST)
    m = Image.new("L", (box, box), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, box - 1, box - 1), 34, fill=255)
    c = Image.new("RGBA", (box, box), (255, 255, 255, 255)); c.putalpha(m); c.alpha_composite(qi, (26, 26))
    b = Image.new("RGBA", (96, 96), (0, 0, 0, 0)); ImageDraw.Draw(b).rounded_rectangle((0, 0, 95, 95), 20, fill=(6, 24, 43, 255))
    b.alpha_composite(logo(76), (10, 8)); c.alpha_composite(b, ((box - 96) // 2, (box - 96) // 2))
    return c
QR = make_qr("https://ark-hvac.com")

IN_C = (24, 44, 70, 255)
def bubble(text, out):
    lines = wrap(text, f_msg, 720); lh = 72
    bw = int(max(f_msg.getlength(l) for l in lines) + 90); bh = int(len(lines) * lh + 60)
    m = Image.new("L", (bw, bh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, bw - 1, bh - 1), 46, fill=255)
    img = grad_img(bw, bh) if out else Image.new("RGBA", (bw, bh), IN_C); img.putalpha(m)
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines): d.text((45, 25 + i * lh), l, font=f_msg, fill=(20, 12, 8) if out else (240, 244, 250))
    return img
def typing(t):
    img = Image.new("RGBA", (170, 100), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 169, 99), 46, fill=IN_C)
    for i in range(3):
        ph = (t * 3.2 - i * .25) % 1; cy = 50 - math.sin(ph * math.pi) * 10
        d.ellipse((50 + i * 35 - 11, cy - 11, 50 + i * 35 + 11, cy + 11), fill=(200, 210, 225, int(120 + 135 * math.sin(ph * math.pi))))
    return img

def chat(base, t, msgs, clock):
    hdr = Image.new("RGBA", (W, 300), (4, 12, 24, 210)); base.alpha_composite(hdr)
    d = ImageDraw.Draw(base)
    d.text((70, 52), clock, font=f_stat, fill=(235, 238, 248))
    d.text((60, 160), "<", font=f_head, fill=(150, 165, 190))
    d.ellipse((120, 135, 220, 235), fill=(6, 24, 43), outline=(255, 150, 50), width=3)
    base.alpha_composite(LOGO_S, (135, 148))
    d.text((250, 140), "New Ark  ·  ark-hvac.com", font=f_head, fill=(245, 245, 250))
    d.text((250, 198), "Replies in minutes, 24/7", font=f_sub, fill=(255, 175, 110))
    items, total = [], 0
    for ts, kind, text, out in msgs:
        if t < ts: continue
        if kind == "typing":
            if t > text: continue
            img = typing(t)
        else: img = bubble(text, out)
        items.append((ts, img, out)); total += img.height + 26
    y = 420 - max(0, 420 + total - 1380)
    for ts, img, out in items:
        a = ease((t - ts) / .28); x = W - 60 - img.width if out else 60
        if y > 300: paste(base, img, a, (x, y + int((1 - a) * 40)))
        y += img.height + 26

CHAT = [(12.4, "msg", "Our heat just died. 2 kids. It's freezing in here.", True),
        (13.6, "typing", 14.4, False),
        (14.5, "msg", "We've got you. What's your address?", False),
        (15.8, "msg", "Phillipsburg, 41 Elm St", True),
        (16.6, "typing", 17.3, False),
        (17.4, "msg", "Booked. Tech at your door 7 AM. Stay warm tonight.", False),
        (19.0, "msg", "Thank you. Seriously.", True)]

def frame(i):
    t = i / FPS
    if t < 11.8: bg = COLD.copy()
    elif t < 20: bg = COLD.copy()
    elif t < 26: k = ease_io((t - 20) / 1.5); bg = COLD * (1 - k) + WARM * k
    else: k = ease_io((t - 26) / .8); bg = WARM * (1 - k) + NAVY * k
    base = Image.fromarray(bg.astype(np.uint8)).convert("RGBA"); d = ImageDraw.Draw(base)

    if t < 4.2:  # thermostat dropping
        a = win(t, 0, 4.2, .6, .35)
        temp = int(round(68 - 14 * ease_io(t / 3.2)))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ld.ellipse((W / 2 - 330, 360, W / 2 + 330, 1020), outline=(120, 170, 230, 120), width=4)
        center(ld, 520, f"{temp}°", f_temp, (190, 220, 255, 255))
        center(ld, 860, "HEAT  OFF", f_stat, (120, 170, 230, 255))
        paste(base, lay, a)
        caption(base, t, 1.4, 4.2, "11:04 PM. The furnace just quit.", 1260, f_capS, (205, 220, 240))
    elif t < 8.6:  # voicemail from other plumbers
        a = win(t, 4.2, 8.6, .4, .4)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        for k, (name, ts) in enumerate([("Plumber #1", 4.4), ("HVAC Guy", 5.4), ("24hr Heating", 6.4)]):
            ka = ease((t - ts) / .3)
            if ka <= 0: continue
            y = 480 + k * 230
            ld.rounded_rectangle((90, y, W - 90, y + 190), 40, fill=(18, 30, 50, int(235 * ka)))
            ld.text((140, y + 36), name, font=f_head, fill=(240, 240, 250, int(255 * ka)))
            ld.text((140, y + 104), "Call failed  ·  Mailbox full", font=f_sub, fill=(255, 110, 100, int(255 * ka)))
            ld.text((W - 250, y + 64), "✕", font=f_head, fill=(255, 110, 100, int(255 * ka))) if False else None
        paste(base, lay, a)
        caption(base, t, 6.9, 8.6, "\"Nobody's picking up.\"", 1300)
    elif t < 11.8:  # shivering beat, then the site
        dim = win(t, 8.6, 11.8, .3, .3)
        caption(base, t, 8.7, 10.4, "Then she found one that answers at midnight.", 760, f_capS, (230, 235, 245))
        sa = ease((t - 10.2) / .5)
        if sa > 0:
            card = Image.new("RGBA", (900, 300), (0, 0, 0, 0)); cd = ImageDraw.Draw(card)
            cd.rounded_rectangle((0, 0, 899, 299), 44, fill=(6, 24, 43, 245), outline=(255, 150, 50, 160), width=3)
            card.alpha_composite(LOGO_S, (50, 50))
            cd.text((140, 50), "ark-hvac.com", font=f_head, fill=(255, 255, 255))
            cd.text((140, 112), "Licensed. Insured. Nearly 40 years.", font=f_sub, fill=(180, 195, 215))
            pill = grad_img(380, 84); pm = Image.new("L", (380, 84), 0)
            ImageDraw.Draw(pm).rounded_rectangle((0, 0, 379, 83), 42, fill=255); pill.putalpha(pm)
            ImageDraw.Draw(pill).text((72, 20), "Message us", font=f_mid, fill=(20, 12, 8))
            card.alpha_composite(pill, (50, 186))
            paste(base, card, sa * dim, ((W - 900) // 2, 1080 + int((1 - sa) * 40)))
    elif t < 20.6:  # the chat
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        chat(lay, t, CHAT, "11:12 PM")
        paste(base, lay, win(t, 11.8, 20.6, .4, .5))
    elif t < 26.2:  # morning payoff
        a = win(t, 20.6, 26.2, .5, .4)
        temp = int(round(54 + 18 * ease_io((t - 21.2) / 2.4)))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        center(ld, 300, "7:02 AM", f_stat, (255, 190, 130, 255))
        ld.ellipse((W / 2 - 300, 380, W / 2 + 300, 980), outline=(255, 150, 50, 150), width=4)
        center(ld, 510, f"{temp}°", f_temp, (255, 210, 160, 255))
        center(ld, 840, "HEAT  ON", f_stat, (255, 160, 80, 255))
        paste(base, lay, a)
        caption(base, t, 22.0, 26.0, "Heat back on before breakfast.", 1130, f_cap)
        caption(base, t, 23.4, 26.0, "Kids in t-shirts. Joe's crew already on to the next call.", 1330, f_capS, (230, 215, 200))
    else:  # end card
        a = ease((t - 26.2) / .7)
        paste(base, LOGO_B, a, ((W - 220) // 2, 230))
        lay = Image.new("RGBA", (W, 300), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        center(ld, 0, "NEW ARK", f_big, (255, 255, 255, 255))
        center(ld, 130, "Plumbing  ·  Heating  ·  Air Conditioning", f_small, (255, 175, 110, 255))
        paste(base, lay, ease((t - 26.4) / .6), (0, 470))
        qa = ease((t - 26.8) / .6)
        paste(base, QR, qa, ((W - QR.width) // 2, 700 + int((1 - qa) * 30)))
        caption(base, t, 27.0, 31, "Scan to message Joe's team", 1095, f_small, (255, 190, 130))
        caption(base, t, 27.4, 31, "ark-hvac.com", 1170, f_url, (255, 255, 255))
        caption(base, t, 27.8, 31, "Message us 24/7  ·  Free estimates", 1290, f_capS, (225, 230, 240))
        caption(base, t, 28.3, 31, "Northern NJ  ·  Licensed & insured  ·  Nearly 40 years", 1420, f_sub, (150, 165, 190))
        caption(base, t, 28.6, 31, "On time. On budget. On spec.", 1520, f_small, (200, 205, 220))

    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < .7: arr *= ease(t / .7)
    if t > 29.5: arr *= clamp((30 - t) / .5)
    return np.clip(arr * VIG + GRAIN[i % 6], 0, 255).astype(np.uint8)

def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr; a = np.zeros(n)
    wind = np.convolve(np.random.default_rng(1).normal(0, 1, n), np.ones(400) / 400, "same") * .35
    a += wind * (0.6 + .4 * np.sin(tt * .9)) * np.clip((11.5 - tt) / 1.5, 0, 1)
    a += .04 * np.sin(2 * np.pi * 98 * tt) * np.clip((12 - tt) / 1.5, 0, 1) * np.clip(tt / 1.5, 0, 1)
    def note(f, t0, dur=2.6, amp=.1):
        i0 = int(t0 * sr); m = min(n - i0, int(dur * sr))
        if m <= 0: return
        x = np.arange(m) / sr; env = np.exp(-x * 2.2) * np.clip(x / .008, 0, 1)
        a[i0:i0 + m] += amp * env * (np.sin(2 * np.pi * f * x) + .4 * np.sin(4 * np.pi * f * x) + .15 * np.sin(6 * np.pi * f * x))
    for k, ts in enumerate([4.4, 5.4, 6.4]):  # failed-call tones
        i0 = int(ts * sr); m = int(.5 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += .12 * np.sin(2 * np.pi * 480 * x) * (x < .22) + .12 * np.sin(2 * np.pi * 620 * x) * (x > .26)
    chords = [(196.0, 246.9, 293.7), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    tc = 12.2
    while tc < 26:
        for ch in chords:
            if tc >= 26: break
            note(ch[0] / 2, tc, 3, .09)
            for k, f in enumerate(ch): note(f, tc + k * .16, 2.4, .055)
            tc += 1.6
    for k, f in enumerate((261.6, 329.6, 392.0, 523.3)): note(f, 26.2 + k * .12, 4, .08)
    note(130.8, 26.2, 4.5, .1)
    for p in [12.4, 14.5, 15.8, 17.4, 19.0]:
        i0 = int(p * sr); m = int(.09 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += .12 * np.sin(2 * np.pi * (900 - 3000 * x) * x) * np.exp(-x * 45)
    a *= np.clip((DUR - tt) / .8, 0, 1)
    a = np.clip(a / np.max(np.abs(a)) * .8, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    out = sys.argv[1]
    if len(sys.argv) > 2:
        for ts in [float(x) for x in sys.argv[2].split(",")]:
            Image.fromarray(frame(int(ts * FPS))).save(f"{out}_{ts:.1f}.png")
        sys.exit()
    audio("/tmp/ark_audio.wav")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", "/tmp/ark_audio.wav", "-c:v", "libx264", "-preset", "veryfast",
                          "-b:v", "7M", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                          "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i in range(N): p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait(); print("done", out)
