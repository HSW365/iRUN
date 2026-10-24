"""QUEENEE micro-drama: "Cents" - 30s, 1080x1920, 30fps."""
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


# ================= QUEENEE micro-drama: "Cents" =================
# 30s, 1080x1920. An indie artist's streaming payout comes in at 2 AM: 48,212 streams, $154.
# His boy texts him: your fans want to pay YOU. QUEENEE builds his site. Tips, members, merch
# and bookings start landing on his phone. QUEENEE builds any website. QR to sign up.
PINK = (236, 72, 153); VIO = (168, 85, 247)
RED = PINK  # chat bubbles for "me" use RED
URL = "https://hsw365.github.io/queenee/?src=ad#signup"
BLUE_NIGHT = vgrad((6, 7, 16), (14, 12, 28))
WARM = vgrad((18, 8, 20), (44, 12, 34))
PINKGLOW = np.exp(-(((xx - W * 0.5) / (W * 0.6)) ** 2 + ((yy - H * 0.38) / (H * 0.32)) ** 2))[..., None].astype(np.float32)

def chat_header(name, sub, clock="2:51"):
    h = Image.new("RGBA", (W, 200), (12, 12, 18, 235)); d = ImageDraw.Draw(h)
    d.text((60, 30), clock, font=I("Inter-SemiBold.otf", 34), fill=WHITE)
    d.text((60, 104), "<", font=I("Inter-Regular.otf", 52), fill=CYAN)
    d.ellipse((120, 96, 190, 166), fill=(*CYAN, 255)); d.text((141 + (28 - tw(B(56), name[0])) / 2 + 2, 101), name[0], font=B(56), fill=INK)
    d.text((212, 100), name, font=I("Inter-SemiBold.otf", 40), fill=WHITE)
    d.text((212, 146), sub, font=I("Inter-Regular.otf", 26), fill=MUT)
    d.line((0, 199, W, 199), fill=LINE, width=2)
    return h

# ---------- payout statement ----------
def payout_card(streams, amount, reveal):
    cw, ch = 880, 1000
    c = rrect((cw, ch), 40, (*CARD, 255), (*LINE, 255)); d = ImageDraw.Draw(c)
    d.text((50, 50), "STREAMING PAYOUT", font=M(32), fill=MUT)
    d.text((50, 96), "Statement  ·  October", font=I("Inter-Medium.otf", 36), fill=(200, 200, 214))
    d.line((50, 170, cw - 50, 170), fill=LINE, width=2)
    d.text((50, 210), "Track", font=I("Inter-Regular.otf", 30), fill=MUT)
    d.text((50, 252), "\"Still Up\"  —  Marcus Vale", font=I("Inter-SemiBold.otf", 42), fill=WHITE)
    d.text((50, 350), "Streams", font=I("Inter-Regular.otf", 30), fill=MUT)
    d.text((50, 388), f"{streams:,}", font=B(150), fill=WHITE)
    d.text((50, 590), "Per stream", font=I("Inter-Regular.otf", 30), fill=MUT)
    d.text((50, 628), "$0.0032", font=M(54), fill=(200, 200, 214))
    d.line((50, 730, cw - 50, 730), fill=LINE, width=2)
    d.text((50, 770), "You earned", font=I("Inter-Regular.otf", 30), fill=MUT)
    col = tuple(int(WHITE[i] + (PINK[i] - WHITE[i]) * reveal) for i in range(3))
    d.text((50, 806), f"${amount:,.2f}", font=B(150), fill=col)
    return c

# ---------- the QUEENEE-built artist site on a phone ----------
PW, PH = 640, 1138
PHONE_MASK = Image.new("L", (PW, PH), 0); ImageDraw.Draw(PHONE_MASK).rounded_rectangle((0, 0, PW - 1, PH - 1), 44, fill=255)
def phone(screen):
    ow, oh = PW + 28, PH + 28
    p = rrect((ow, oh), 58, (34, 34, 44, 255), (70, 70, 84, 255), 3)
    s = screen.convert("RGBA"); s.putalpha(PHONE_MASK); p.alpha_composite(s, (14, 14))
    return p

def site_screen(lt):
    """Artist site, scrolls as lt goes 0..1."""
    full_h = 2300
    sc = Image.new("RGBA", (PW, full_h), (10, 10, 15, 255)); d = ImageDraw.Draw(sc)
    # cover
    cov = Image.new("RGBA", (PW, 760), (0, 0, 0, 0)); cg = np.zeros((760, PW, 4), np.uint8)
    yv = np.linspace(0, 1, 760)[:, None]; xv = np.linspace(0, 1, PW)[None, :]
    r = np.clip(40 + 150 * np.exp(-((xv - 0.7) ** 2 / 0.08 + (yv - 0.3) ** 2 / 0.1)) , 0, 255)
    g = np.clip(14 + 40 * np.exp(-((xv - 0.7) ** 2 / 0.08 + (yv - 0.3) ** 2 / 0.1)), 0, 255)
    b = np.clip(40 + 120 * np.exp(-((xv - 0.25) ** 2 / 0.1 + (yv - 0.6) ** 2 / 0.12)), 0, 255)
    cg[..., 0] = r; cg[..., 1] = g; cg[..., 2] = b; cg[..., 3] = 255
    cov = Image.fromarray(cg, "RGBA")
    fade = Image.new("RGBA", (PW, 760), (0, 0, 0, 0)); fd = np.zeros((760, PW, 4), np.uint8)
    fd[..., 3] = (np.clip((yv - 0.45) / 0.55, 0, 1) * 255).astype(np.uint8).repeat(PW, 1); fd[..., :3] = (10, 10, 15)
    cov.alpha_composite(Image.fromarray(fd, "RGBA"))
    sc.alpha_composite(cov, (0, 0))
    d.text((36, 40), "MARCUS VALE", font=M(24), fill=WHITE)
    d.text((PW - 36 - tw(M(24), "MENU"), 40), "MENU", font=M(24), fill=WHITE)
    tag = rrect((290, 50), 25, (*PINK, 255)); ImageDraw.Draw(tag).text((22, 10), "NEW SINGLE OUT NOW", font=M(20), fill=WHITE)
    sc.alpha_composite(tag, (36, 420))
    d.text((32, 480), "STILL UP", font=B(150), fill=WHITE)
    for k, lab in enumerate(("Listen", "Watch", "Book me")):
        bb = rrect((170, 66), 33, (255, 255, 255, 255) if k == 0 else (255, 255, 255, 30), None if k == 0 else (255, 255, 255, 120), 2)
        ImageDraw.Draw(bb).text(((170 - tw(I("Inter-SemiBold.otf", 26), lab)) / 2, 17), lab, font=I("Inter-SemiBold.otf", 26), fill=INK if k == 0 else WHITE)
        sc.alpha_composite(bb, (36 + k * 186, 670))
    y = 790
    # player
    pl = rrect((PW - 72, 130), 26, (*CARD, 255), (*LINE, 255)); pd = ImageDraw.Draw(pl)
    pd.ellipse((24, 25, 104, 105), fill=(*PINK, 255)); pd.polygon([(54, 45), (54, 85), (86, 65)], fill=WHITE)
    pd.text((128, 26), "Still Up", font=I("Inter-SemiBold.otf", 30), fill=WHITE)
    for k in range(34):
        hgt = 8 + 26 * abs(math.sin(k * 0.9 + lt * 12))
        pd.rounded_rectangle((128 + k * 12, 92 - hgt / 2, 134 + k * 12, 92 + hgt / 2), 3, fill=(*PINK, 255) if k < 14 else (70, 70, 84, 255))
    sc.alpha_composite(pl, (36, y)); y += 170
    # support / tip jar
    d.text((36, y), "SUPPORT THE MUSIC", font=M(24), fill=MUT); y += 46
    for k, amt in enumerate(("$5", "$10", "$20", "$50")):
        bb = rrect((128, 92), 22, (*(PINK if k == 2 else (26, 26, 37)), 255), (*LINE, 255))
        ImageDraw.Draw(bb).text(((128 - tw(B(52), amt)) / 2, 14), amt, font=B(52), fill=WHITE)
        sc.alpha_composite(bb, (36 + k * 144, y))
    y += 130
    # membership
    mb = rrect((PW - 72, 220), 26, (26, 18, 36, 255), (*VIO, 255), 2); md = ImageDraw.Draw(mb)
    md.text((28, 24), "INNER CIRCLE", font=M(24), fill=(*VIO, 255))
    md.text((28, 62), "Early drops. Unreleased", font=I("InterDisplay-SemiBold.otf", 36), fill=WHITE)
    md.text((28, 106), "music. Front row.", font=I("InterDisplay-SemiBold.otf", 36), fill=WHITE)
    jb = rrect((200, 56), 28, (*VIO, 255)); ImageDraw.Draw(jb).text((52, 13), "Join now", font=I("Inter-SemiBold.otf", 26), fill=WHITE)
    mb.alpha_composite(jb, (28, 154)); sc.alpha_composite(mb, (36, y)); y += 260
    # merch
    d.text((36, y), "MERCH", font=M(24), fill=MUT); d.text((PW - 36 - tw(M(24), "SHOP ALL"), y), "SHOP ALL", font=M(24), fill=PINK); y += 46
    for k, (nm, colr) in enumerate((("Tour Tee", (30, 30, 40)), ("Hoodie", (40, 22, 40)), ("Vinyl", (22, 26, 40)))):
        mc = rrect((178, 220), 20, (*colr, 255), (*LINE, 255)); mdd = ImageDraw.Draw(mc)
        if nm == "Vinyl":
            mdd.ellipse((34, 24, 144, 134), fill=(8, 8, 12, 255)); mdd.ellipse((74, 64, 104, 94), fill=(*PINK, 255))
        else:
            s_ = 1.1; pts = [(30, 12), (40, 8), (44, 13), (56, 13), (60, 8), (70, 12), (90, 26), (82, 40), (73, 35), (73, 92), (27, 92), (27, 35), (18, 40), (10, 26)]
            mdd.polygon([(x * s_ + 34, y_ * s_ + 18) for x, y_ in pts], fill=(14, 14, 18, 255), outline=(80, 80, 92, 255))
            mdd.text((89 - tw(B(26), "MV") / 2, 70), "MV", font=B(26), fill=PINK)
        mdd.text((16, 170), nm, font=I("Inter-SemiBold.otf", 26), fill=WHITE)
        sc.alpha_composite(mc, (36 + k * 196, y))
    y += 260
    d.text((36, y), "TOUR DATES", font=M(24), fill=MUT); y += 46
    for k, (dt, city) in enumerate((("NOV 14", "Newark, NJ"), ("NOV 22", "Philadelphia, PA"), ("DEC 06", "Brooklyn, NY"))):
        d.text((36, y), dt, font=M(26), fill=PINK); d.text((180, y - 2), city, font=I("Inter-SemiBold.otf", 30), fill=WHITE)
        d.line((36, y + 56, PW - 36, y + 56), fill=LINE, width=2); y += 76
    off = int(ease(clamp((lt - 0.25) / 0.65)) * (full_h - PH - 120))
    return sc.crop((0, off, PW, off + PH))

# ---------- notifications ----------
NOTES = [("TIP", "$20 from @keisha.b", "\"this song got me thru the week\"", PINK),
         ("MEMBER", "New Inner Circle member", "@dre_vibes joined", VIO),
         ("ORDER", "Tour Tee x2 + Vinyl", "Shipping to Atlanta, GA", CYAN),
         ("TIP", "$50 from @lowkeylena", "\"run it back\"", PINK),
         ("BOOKING", "Show request: Sat, Nov 29", "The Loft, Jersey City", GOLD)]
def note_card(kind, title, sub, col):
    c = rrect((W - 120, 170), 34, (24, 24, 34, 240), (*LINE, 255)); d = ImageDraw.Draw(c)
    ic = rrect((96, 96), 24, (*col, 255)); idd = ImageDraw.Draw(ic)
    idd.text(((96 - tw(B(64), "MV")) / 2, 10), "MV", font=B(64), fill=INK)
    c.alpha_composite(ic, (30, 37))
    d.text((150, 30), f"MARCUS VALE  ·  {kind}", font=M(24), fill=col)
    d.text((150, 66), title, font=I("Inter-SemiBold.otf", 38), fill=WHITE)
    d.text((150, 116), sub, font=I("Inter-Regular.otf", 30), fill=(190, 190, 204))
    d.text((W - 120 - 30 - tw(I("Inter-Regular.otf", 26), "now"), 32), "now", font=I("Inter-Regular.otf", 26), fill=MUT)
    return c

# ---------- QR ----------
def qr_card(box=420):
    import segno
    buf = io.BytesIO(); segno.make(URL, error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
    code = Image.open(buf).convert("RGBA").resize((box - 60, box - 60), Image.NEAREST)
    c = rrect((box, box), 36, (255, 255, 255, 255)); c.alpha_composite(code, (30, 30))
    badge = rrect((96, 96), 22, (*PINK, 255)); bd = ImageDraw.Draw(badge)
    bf = B(70); bd.text(((96 - tw(bf, "Q")) / 2, 4), "Q", font=bf, fill=WHITE)
    wb = rrect((112, 112), 26, (255, 255, 255, 255)); wb.alpha_composite(badge, (8, 8))
    c.alpha_composite(wb, ((box - 112) // 2, (box - 112) // 2))
    return c
QR = qr_card()

WHO = ["ARTISTS", "BARBERS", "RESTAURANTS", "CHURCHES", "COACHES", "CLOTHING LINES", "CONTRACTORS", "PODCASTS"]

def finish(arr, i):
    arr = arr * VIG + GRAIN[i % 6]
    return np.clip(arr, 0, 255).astype(np.uint8)

def headline(base, t, a, b, text, y, size, fill):
    k = win(t, a, b)
    if k <= 0: return
    f = B(size)
    while tw(f, text) > W - 110: size -= 4; f = B(size)
    lay = Image.new("RGBA", (W, int(size * 1.3)), (0, 0, 0, 0))
    ctext(ImageDraw.Draw(lay), 0, text, f, fill)
    paste(base, lay, k, (0, y + 18 * (1 - k)))

CUTS = (3.6, 8.6, 11.6, 19.6, 24.2, 26.6)
def frame(i):
    t = i / FPS
    if t < 11.6: bg = BLUE_NIGHT.copy()
    elif t < 24.2: bg = BLUE_NIGHT * 0.85 + WARM * 0.15 + PINKGLOW * np.array([70, 14, 44], np.float32) * win(t, 11.6, 24.2, 0.6, 0.6)
    else: bg = BLUE_NIGHT * 0.55 + WARM * 0.45
    base = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")

    # A: 2:46 AM, release week
    k = win(t, 0.2, 3.7, 0.6, 0.4)
    if k:
        lay = Image.new("RGBA", (W, 620), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "Release week", I("Inter-Medium.otf", 44), MUT)
        ctext(ld, 60, "2:46", I("InterDisplay-Thin.otf", 300), WHITE)
        paste(base, lay, k, (0, 540))
        caption(base, t, 1.0, 3.7, "200 nights in the booth. Payout day.", 1300, I("InterDisplay-Medium.otf", 54), (210, 210, 222))

    # B: payout
    k = win(t, 3.6, 8.7, 0.45, 0.35)
    if k:
        st = int(48212 * ease(clamp((t - 4.0) / 1.6)))
        amt = st * 0.0032
        rev = clamp((t - 6.0) / 0.5)
        card = payout_card(st, amt, rev)
        s = 0.96 + 0.04 * ease((t - 3.6) / 5)
        card = card.resize((int(card.width * s), int(card.height * s)), Image.LANCZOS)
        paste(base, card, k, ((W - card.width) / 2, 300 - 20 * (1 - k)))
        headline(base, t, 6.2, 8.7, "SPOTIFY PAYS CENTS.", 1400, 130, WHITE)
        caption(base, t, 6.9, 8.7, "48,212 streams. $154.", 1590, I("InterDisplay-SemiBold.otf", 56), (210, 210, 222))

    # C: Mo texts
    k = win(t, 8.6, 11.7, 0.3, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(chat_header("Mo", "online"), (0, 0))
        b1 = bubble("48k streams and you STILL don't got a website??", False)
        b2 = bubble("your fans wanna pay YOU. not the app.", False)
        b3 = bubble("QUEENEE built mine. took a week", False)
        b4 = bubble("send me the link", True)
        y = 290
        for bb, ts, mine in ((b1, 8.75, False), (b2, 9.45, False), (b3, 10.1, False), (b4, 10.8, True)):
            if t >= ts:
                a = ease((t - ts) / 0.22); x = W - 60 - bb.width if mine else 60
                lay.alpha_composite(alpha(bb, a), (int(x), int(y + 20 * (1 - a))))
            y += bb.height + 26
        paste(base, lay, k)

    # D: his site
    k = win(t, 11.5, 19.8, 0.4, 0.3)
    if k:
        lt = (t - 11.6) / 8.0
        ph = phone(site_screen(lt))
        sc = 0.92 + 0.08 * ease((t - 11.5) / 0.6)
        ph2 = ph.resize((int(ph.width * sc), int(ph.height * sc)), Image.LANCZOS)
        paste(base, ph2, k, ((W - ph2.width) / 2, 330 + (ph.height - ph2.height) / 2))
        lay = Image.new("RGBA", (W, 220), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "ONE WEEK LATER", M(30), MUT)
        ctext(ld, 44, "HIS OWN STATION", B(104), WHITE)
        paste(base, lay, k, (0, 110))
        caption(base, t, 12.2, 15.8, "Built by QUEENEE.", 1560, I("InterDisplay-SemiBold.otf", 62))
        caption(base, t, 15.9, 19.8, "Tips. Members. Merch. Bookings.", 1560, I("InterDisplay-SemiBold.otf", 58))
        caption(base, t, 12.5, 19.8, "His music. His fans. His money.", 1660, I("InterDisplay-Medium.otf", 42), MUT)

    # E: notifications land
    k = win(t, 19.6, 24.3, 0.3, 0.35)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 140, "Saturday", I("Inter-Medium.otf", 40), MUT)
        ctext(ld, 190, "9:14", I("InterDisplay-Thin.otf", 200), WHITE)
        y = 470
        for n, nt in enumerate(NOTES):
            ts = 19.9 + n * 0.62
            if t >= ts:
                a = ease((t - ts) / 0.25)
                c = note_card(*nt)
                lay.alpha_composite(alpha(c, a), (60, int(y - 40 * (1 - a))))
            y += 196
        paste(base, lay, k)
        headline(base, t, 22.6, 24.3, "YOUR LISTENERS PAY YOU.", 1500, 120, PINK)

    # F: any website
    k = win(t, 24.2, 26.8, 0.25, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 520, "QUEENEE BUILDS", M(44), MUT)
        ctext(ld, 590, "ANY WEBSITE", B(170), WHITE)
        idx = int((t - 24.25) / 0.28) % len(WHO)
        word = WHO[idx]
        ctext(ld, 860, "FOR", M(40), MUT)
        ctext(ld, 920, word, B(150), PINK)
        ctext(ld, 1150, "and anyone with something to put out.", I("InterDisplay-Medium.otf", 46), (210, 210, 222))
        paste(base, lay, k)

    # G: end card
    k = win(t, 26.6, 31, 0.45, 0.1)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 150, "HSW365 MEDIA", M(44), PINK)
        ctext(ld, 205, "QUEENEE", B(200), WHITE)
        ctext(ld, 430, "Your own website. Built for you.", I("InterDisplay-Medium.otf", 46), (210, 210, 222))
        lay.alpha_composite(QR, ((W - QR.width) // 2, 560))
        ctext(ld, 1012, "SCAN TO SIGN UP", B(76), CYAN)
        pills = ["Artists", "Businesses", "Anyone"]
        pw = 270; gx = (W - pw * 3 - 30) // 2
        for n, p_ in enumerate(pills):
            c = rrect((pw, 84), 42, (*CARD, 255), (*(PINK if n == 0 else LINE), 255), 3)
            ctext(ImageDraw.Draw(c), 22, p_, I("Inter-SemiBold.otf", 34), WHITE, 0, pw)
            lay.alpha_composite(c, (gx + n * (pw + 15), 1130))
        ctext(ld, 1290, "hsw365.github.io/queenee", M(40), WHITE)
        ctext(ld, 1356, "Card, Cash App or Zelle  ·  You approve it before it goes live", I("Inter-Medium.otf", 32), MUT)
        ctext(ld, 1720, "HSW365 Media  ·  Turn Negative Into Positive", I("Inter-Medium.otf", 30), (120, 120, 140))
        paste(base, lay, k, (0, 20 * (1 - k)))

    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < 0.5: arr *= clamp(t / 0.5)
    if t > 29.6: arr *= clamp((30 - t) / 0.4)
    for tc in CUTS:
        if 0 <= t - tc < 0.12: arr = arr * 0.6 + 255 * 0.4 * (1 - (t - tc) / 0.12)
    return finish(arr, i)

# ---------- audio: lonely keys -> beat drops when the site appears ----------
def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr; a = np.zeros(n)
    def note(t0, f, dur, amp):
        i0 = int(t0 * sr); m = int(dur * sr); x = np.arange(m) / sr
        if i0 + m < n:
            a[i0:i0 + m] += amp * (np.sin(2 * np.pi * f * x) + 0.35 * np.sin(4 * np.pi * f * x) + 0.12 * np.sin(6 * np.pi * f * x)) * np.exp(-x * 2.2) * np.clip(x / 0.01, 0, 1)
    # sad Rhodes-ish chords 0-11.6 (Am - F - C - G) every 2.9s
    chords = [(220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 261.6, 329.6), (196.0, 246.9, 293.7)]
    for c in range(4):
        for f in chords[c]: note(0.3 + c * 2.85, f, 2.8, 0.05)
        note(0.3 + c * 2.85, chords[c][0] / 2, 2.8, 0.06)
    a += 0.03 * np.sin(2 * np.pi * 55 * tt) * np.clip(tt / 1.5, 0, 1) * np.clip((11.6 - tt) / 0.6, 0, 1)
    # cash-register-sad blip on payout reveal
    for p_, f in ((6.0, 440), (6.18, 349)):
        i0 = int(p_ * sr); m = int(0.25 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.12 * np.sin(2 * np.pi * f * x) * np.exp(-x * 9)
    # beat from 11.6 at 90 bpm
    spb = 60 / 90
    def kick(t0):
        i0 = int(t0 * sr); m = int(0.35 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += 0.6 * np.sin(2 * np.pi * (110 * np.exp(-x * 20) + 45) * x) * np.exp(-x * 7)
    def hat(t0, amp=0.05):
        i0 = int(t0 * sr); m = int(0.05 * sr)
        if i0 + m < n: a[i0:i0 + m] += amp * rng.normal(0, 1, m) * np.exp(-np.arange(m) / sr * 80)
    def snare(t0):
        i0 = int(t0 * sr); m = int(0.22 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += (0.2 * rng.normal(0, 1, m) + 0.2 * np.sin(2 * np.pi * 190 * x)) * np.exp(-x * 20)
    prog = [(220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (261.6, 329.6, 392.0), (196.0, 246.9, 293.7)]
    beat = 0; tb = 11.6
    while tb < 29.3:
        if beat % 4 == 0 or beat % 8 == 5: kick(tb)
        if beat % 4 == 2: snare(tb)
        hat(tb + spb / 2); hat(tb, 0.03)
        if beat % 4 == 0:
            ch = prog[(beat // 4) % 4]
            for f in ch: note(tb, f, spb * 4, 0.035)
            note(tb, ch[0] / 4, spb * 3.5, 0.11)
        tb += spb; beat += 1
    for tc in CUTS:
        i0 = int((tc - 0.25) * sr); m = int(0.5 * sr); x = np.arange(m) / sr
        env = np.sin(np.pi * x / 0.5) ** 2
        a[i0:i0 + m] += 0.12 * np.convolve(rng.normal(0, 1, m), np.ones(12) / 12, "same") * env
    for p_ in (8.75, 9.45, 10.1, 10.8):
        i0 = int(p_ * sr); m = int(0.09 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.18 * np.sin(2 * np.pi * (950 - 3000 * x) * x) * np.exp(-x * 45)
    # notification chimes (bright, two-tone)
    for kk in range(len(NOTES)):
        t0 = 19.9 + kk * 0.62
        for f, dt in ((1318.5, 0), (1760.0, 0.08)):
            i0 = int((t0 + dt) * sr); m = int(0.3 * sr); x = np.arange(m) / sr
            a[i0:i0 + m] += 0.1 * np.sin(2 * np.pi * f * x) * np.exp(-x * 12)
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
