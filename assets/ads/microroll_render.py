"""HSW365 Tear-Off Microfiber Roll micro-drama: "The Last Paper Towel" - 25s, 1080x1920, 30fps.
7:42 AM. Dre knocks a full glass of orange juice across the counter. He grabs for the paper towels:
empty tube. Third pack this month. His homie Mook texts "stop buying paper towels" and slides the
HSW365 roll across the counter. One rip, one wipe, spill gone. Cloth goes in the wash, back on the roll.
"Bro... I been throwing money in the trash." End card: $10.99, QR to subscribe, hsw365.co.
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from queenee_render import *  # shared helpers: fonts, gradients, bubble, rrect, wrap, finish, headline...
import queenee_render as Q

DUR = 25.0
N = int(FPS * DUR)
TEAL = (20, 184, 166); OJ = (251, 146, 36); OJ_D = (214, 104, 14)
ACC = TEAL
Q.RED = TEAL  # "my" chat bubbles
URL = "https://hsw365.co/products/hsw365-tear-off-microfiber-cleaning-roll-30-sheets?src=ig-microdrama"
MORNING = vgrad((24, 20, 18), (44, 34, 28))
NIGHT2 = vgrad((6, 8, 12), (12, 18, 22))
TEALGLOW = np.exp(-(((xx - W * 0.5) / (W * 0.6)) ** 2 + ((yy - H * 0.42) / (H * 0.3)) ** 2))[..., None].astype(np.float32)
COUNTER_Y = 1180


def chat_header2(name, sub, clock):
    h = Image.new("RGBA", (W, 200), (12, 12, 18, 235)); d = ImageDraw.Draw(h)
    d.text((60, 30), clock, font=I("Inter-SemiBold.otf", 34), fill=WHITE)
    d.text((60, 104), "<", font=I("Inter-Regular.otf", 52), fill=CYAN)
    d.ellipse((120, 96, 190, 166), fill=(*GOLD, 255))
    d.text((155 - tw(B(56), name[0]) / 2, 101), name[0], font=B(56), fill=INK)
    d.text((212, 100), name, font=I("Inter-SemiBold.otf", 40), fill=WHITE)
    d.text((212, 146), sub, font=I("Inter-Regular.otf", 26), fill=MUT)
    d.line((0, 199, W, 199), fill=LINE, width=2)
    return h


# ---------- kitchen ----------
def counter():
    c = Image.new("RGBA", (W, H - COUNTER_Y), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    for y in range(c.height):
        k = y / c.height
        d.line((0, y, W, y), fill=(int(58 - 26 * k), int(52 - 24 * k), int(48 - 22 * k), 255))
    d.line((0, 0, W, 0), fill=(120, 110, 100, 255), width=4)
    for n in range(7):  # faint marble veins
        x0 = 60 + n * 160
        d.line((x0, 10, x0 + 140, 200 + n * 30), fill=(90, 82, 76, 120), width=2)
    return c
COUNTER = counter()


def glass(angle, fill_k):
    g = Image.new("RGBA", (220, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
    lvl = int(40 + 200 * (1 - fill_k))
    d.rounded_rectangle((20, lvl, 200, 290), 18, fill=(*OJ, 235))
    d.rounded_rectangle((14, 0, 206, 296), 22, outline=(230, 236, 240, 200), width=6)
    d.line((40, 30, 40, 250), fill=(255, 255, 255, 90), width=8)
    return g.rotate(angle, resample=Image.BICUBIC, expand=True)


def puddle(k, shrink=0.0, wipe_x=None):
    """Spreading juice on the counter. shrink 0..1 = how much has been wiped up."""
    if k <= 0: return None
    lay = Image.new("RGBA", (W, 260), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    rx = 120 + 330 * ease(k); ry = 30 + 46 * ease(k)
    cx = 470 + 80 * ease(k); cy = 110
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(*OJ_D, 230))
    d.ellipse((cx - rx * 0.8, cy - ry * 0.7, cx + rx * 0.6, cy + ry * 0.4), fill=(*OJ, 210))
    for n in range(5):
        bx = cx - rx + 40 + n * rx * 0.42; d.ellipse((bx, cy - 6, bx + 26, cy + 8), fill=(255, 210, 150, 160))
    if shrink > 0:  # wiped region clears left -> right
        m = Image.new("L", lay.size, 255); md = ImageDraw.Draw(m)
        edge = cx - rx + (2 * rx + 40) * ease(shrink)
        md.rectangle((0, 0, edge, lay.height), fill=0)
        lay.putalpha(Image.composite(lay.getchannel("A"), Image.new("L", lay.size, 0), m))
    return lay


def empty_holder(shake):
    c = Image.new("RGBA", (420, 520), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    d.rounded_rectangle((185, 0, 235, 500), 20, fill=(180, 186, 196, 255))   # chrome post
    d.rounded_rectangle((60, 470, 360, 516), 22, fill=(150, 156, 166, 255))  # base
    d.rounded_rectangle((120 + shake, 120, 300 + shake, 430), 24, fill=(166, 120, 72, 255))  # cardboard tube
    d.rounded_rectangle((120 + shake, 120, 300 + shake, 150), 14, fill=(140, 98, 58, 255))
    for n in range(5):
        y = 170 + n * 54; d.line((126 + shake, y, 294 + shake, y + 28), fill=(140, 98, 58, 200), width=4)
    d.rectangle((150 + shake, 360, 270 + shake, 372), fill=(240, 240, 240, 255))  # the one sad scrap
    return c


def receipt(k):
    c = rrect((W - 160, 300), 30, (240, 238, 232, 255)); d = ImageDraw.Draw(c)
    f = M(30); fb = M(36)
    d.text((44, 34), "PAPER TOWELS  12 ROLL", font=f, fill=(40, 40, 40))
    d.text((44, 84), "OCT 03 ........ $24.99", font=f, fill=(40, 40, 40))
    if k > 0.35: d.text((44, 130), "OCT 14 ........ $24.99", font=f, fill=(40, 40, 40))
    if k > 0.7: d.text((44, 176), "OCT 24 ........ $24.99", font=f, fill=(40, 40, 40))
    if k > 0.95:
        d.line((44, 228, W - 204, 228), fill=(120, 120, 120), width=2)
        d.text((44, 240), "3RD PACK THIS MONTH", font=fb, fill=(200, 40, 40))
    return c


# ---------- the product ----------
def roll(tear_k, sheets_left_label=True):
    """Front view of the tear-off roll on a counter: cylinder + a sheet pulling off along the perforation."""
    c = Image.new("RGBA", (900, 760), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    # shadow
    d.ellipse((90, 640, 810, 720), fill=(0, 0, 0, 110))
    # cylinder body (gray microfiber)
    for x in range(140, 760):
        s = 0.55 + 0.45 * math.sin(math.pi * (x - 140) / 620)
        col = (int(118 * s + 30), int(128 * s + 30), int(138 * s + 34), 255)
        d.line((x, 170, x, 610), fill=col)
    d.ellipse((90, 170, 190, 610), fill=(96, 104, 114, 255))     # left cap
    d.ellipse((112, 300, 168, 480), fill=(56, 60, 68, 255))      # core
    d.ellipse((710, 170, 810, 610), fill=(150, 160, 170, 255))   # right cap
    # waffle texture
    for y in range(190, 600, 22):
        d.line((150, y, 750, y), fill=(255, 255, 255, 18), width=2)
    # brand band
    band = rrect((360, 90), 20, (*TEAL, 255)); bd = ImageDraw.Draw(band)
    bd.text(((360 - tw(B(64), "HSW365")) / 2, 8), "HSW365", font=B(64), fill=INK)
    c.alpha_composite(band, (270, 345))
    # hanging sheet tearing off
    lift = ease(tear_k)
    sh = Image.new("RGBA", (560, 420), (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
    sd.rounded_rectangle((0, 0, 559, 419), 10, fill=(156, 168, 180, 255))
    for y in range(10, 410, 22):
        sd.line((10, y, 550, y), fill=(255, 255, 255, 22), width=2)
    for x in range(0, 560, 26):  # perforation
        sd.line((x, 0, x + 12, 0), fill=(60, 66, 74, 255), width=6)
    sh = sh.rotate(-18 * lift, resample=Image.BICUBIC, expand=True)
    c.alpha_composite(sh, (int(170 + 220 * lift), int(560 + 60 * lift - 40 * math.sin(math.pi * lift))))
    return c


def pill(text, col):
    f = I("Inter-SemiBold.otf", 36)
    pw = int(tw(f, text)) + 70
    c = rrect((pw, 86), 43, (*CARD, 255), (*col, 255), 3)
    ImageDraw.Draw(c).text((35, 20), text, font=f, fill=WHITE)
    return c
PILLS = [("30 SHEETS", TEAL), ("WASH + REUSE", CYAN), ("LINT-FREE", GOLD)]


def washer(t):
    c = Image.new("RGBA", (520, 560), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, 519, 559), 40, fill=(228, 230, 236, 255))
    d.rounded_rectangle((0, 0, 519, 110), 40, fill=(206, 210, 218, 255)); d.rectangle((0, 70, 519, 110), fill=(206, 210, 218, 255))
    d.ellipse((380, 30, 440, 90), fill=(160, 166, 176, 255)); d.rounded_rectangle((60, 44, 260, 74), 12, fill=(40, 44, 54, 255))
    d.text((76, 44), "WASH  40°", font=M(24), fill=(*TEAL, 255))
    d.ellipse((80, 150, 440, 510), fill=(150, 156, 168, 255)); d.ellipse((110, 180, 410, 480), fill=(24, 40, 52, 255))
    cx, cy = 260, 330
    for n in range(3):  # cloths tumbling
        a = t * 5.0 + n * 2.1
        x = cx + 95 * math.cos(a); y = cy + 95 * math.sin(a)
        d.rounded_rectangle((x - 46, y - 30, x + 46, y + 30), 10, fill=(*(TEAL if n == 0 else (156, 168, 180)), 255))
    d.ellipse((140, 210, 230, 260), fill=(255, 255, 255, 40))
    return c


def qr_card2(box=420):
    import segno
    buf = io.BytesIO(); segno.make(URL, error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
    code = Image.open(buf).convert("RGBA").resize((box - 60, box - 60), Image.NEAREST)
    c = rrect((box, box), 36, (255, 255, 255, 255)); c.alpha_composite(code, (30, 30))
    badge = rrect((96, 96), 22, (*ACC, 255)); bd = ImageDraw.Draw(badge)
    bf = B(56); bd.text(((96 - tw(bf, "HSW")) / 2, 14), "HSW", font=bf, fill=INK)
    wb = rrect((112, 112), 26, (255, 255, 255, 255)); wb.alpha_composite(badge, (8, 8))
    c.alpha_composite(wb, ((box - 112) // 2, (box - 112) // 2))
    return c
QR2 = qr_card2()

CUTS = (4.2, 8.0, 11.4, 16.2, 19.6)


def frame(i):
    t = i / FPS
    if t < 11.4: bg = MORNING
    elif t < 19.6: bg = NIGHT2 + TEALGLOW * np.array([10, 46, 42], np.float32) * win(t, 11.4, 19.6, 0.6, 0.6)
    else: bg = NIGHT2 + TEALGLOW * np.array([6, 30, 28], np.float32)
    base = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")

    # A: 7:42 AM, the spill
    k = win(t, 0.2, 4.3, 0.5, 0.35)
    if k:
        lay = Image.new("RGBA", (W, 440), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "Monday. Running late.", I("Inter-Medium.otf", 44), MUT)
        ctext(ld, 60, "7:42", I("InterDisplay-Thin.otf", 300), WHITE)
        paste(base, lay, k, (0, 220))
        paste(base, COUNTER, k, (0, COUNTER_Y))
        tip = ease((t - 1.3) / 0.5)
        g = glass(-82 * tip, 1 - 0.85 * tip)
        paste(base, g, k, (360 - 60 * tip, COUNTER_Y - g.height + 6 + 40 * tip))
        p = puddle(clamp((t - 1.6) / 1.4))
        if p: paste(base, p, k, (0, COUNTER_Y + 10))
        headline(base, t, 2.2, 4.3, "NAH. NOT TODAY.", 1560, 130, OJ)

    # B: grabs the paper towels - empty. Receipt.
    k = win(t, 4.2, 8.1, 0.3, 0.3)
    if k:
        shake = int(10 * math.sin(t * 60) * clamp(1 - (t - 4.4) / 0.6)) if t > 4.4 else 0
        paste(base, empty_holder(shake), k, ((W - 420) // 2, 260))
        headline(base, t, 4.9, 8.1, "EMPTY. AGAIN.", 820, 140, WHITE)
        paste(base, receipt(clamp((t - 5.6) / 1.8)), k * win(t, 5.4, 8.1, 0.3, 0.3), (80, 1040))
        caption(base, t, 7.0, 8.1, "That's $75 he literally threw away.", 1400, I("InterDisplay-SemiBold.otf", 52), (230, 120, 110))

    # C: text from Mook
    k = win(t, 8.0, 11.5, 0.3, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(chat_header2("Mook", "roommate", "7:44"), (0, 0))
        msgs = [(mybubble_("out of paper towels AGAIN"), 8.15, True),
                (bubble("bro stop buying paper towels", False), 8.85, False),
                (bubble("check the counter. I left you something", False), 9.65, False),
                (mybubble_("...a roll of RAGS?"), 10.45, True)]
        y = 290
        for bb, ts, mine in msgs:
            if t >= ts:
                a = ease((t - ts) / 0.22); x = W - 60 - bb.width if mine else 60
                lay.alpha_composite(alpha(bb, a), (int(x), int(y + 20 * (1 - a))))
            y += bb.height + 26
        paste(base, lay, k)

    # D: rip, wipe, gone
    k = win(t, 11.4, 16.3, 0.35, 0.3)
    if k:
        lay = Image.new("RGBA", (W, 230), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "ONE RIP.", B(150), WHITE)
        paste(base, lay, k * win(t, 11.4, 13.4, 0.3, 0.3), (0, 200))
        lay2 = Image.new("RGBA", (W, 230), (0, 0, 0, 0)); ld2 = ImageDraw.Draw(lay2)
        ctext(ld2, 0, "ONE WIPE.", B(150), TEAL)
        paste(base, lay2, k * win(t, 13.3, 16.3, 0.3, 0.3), (0, 200))
        r = roll(clamp((t - 11.9) / 0.9))
        paste(base, r, k * win(t, 11.4, 13.4, 0.3, 0.4), ((W - r.width) // 2, 470))
        # the wipe
        wk = win(t, 13.3, 16.3, 0.3, 0.3)
        if wk:
            paste(base, COUNTER, wk, (0, COUNTER_Y - 300))
            sw = clamp((t - 13.6) / 1.4)
            p = puddle(1.0, shrink=sw)
            paste(base, p, wk, (0, COUNTER_Y - 290))
            cl = rrect((240, 160), 18, (156, 168, 180, 255)); cd = ImageDraw.Draw(cl)
            for yy_ in range(12, 150, 20): cd.line((10, yy_, 230, yy_), fill=(255, 255, 255, 26), width=2)
            cl = cl.rotate(-8 + 10 * math.sin(t * 9), resample=Image.BICUBIC, expand=True)
            paste(base, cl, wk, (60 + 760 * ease(sw), COUNTER_Y - 330 + 14 * math.sin(t * 18)))
            if t > 15.1:
                for n, (txt, col) in enumerate(PILLS):
                    ts = 15.1 + n * 0.25
                    if t >= ts:
                        pl = pill(txt, col); a = ease((t - ts) / 0.25)
                        paste(base, pl, a * wk, ((W - pl.width) // 2, 1340 + n * 110 + 20 * (1 - a)))
        caption(base, t, 14.6, 16.3, "Gone. Streak-free.", 560, I("InterDisplay-SemiBold.otf", 64))

    # E: wash it, back on the roll, the line
    k = win(t, 16.2, 19.7, 0.3, 0.3)
    if k:
        wsh = washer(t)
        paste(base, wsh, k, ((W - wsh.width) // 2, 300))
        caption(base, t, 16.4, 19.7, "Toss it in the wash. Use it again.", 900, I("InterDisplay-Medium.otf", 50), (210, 210, 222))
        q = Image.new("RGBA", (W, 420), (0, 0, 0, 0)); qd = ImageDraw.Draw(q)
        f = I("InterDisplay-SemiBold.otf", 66)
        for n, ln in enumerate(wrap("\"Bro... I been throwing money in the trash.\"", f, W - 160)):
            ctext(qd, n * 84, ln, f, WHITE)
        paste(base, q, win(t, 17.3, 19.7, 0.35, 0.3), (0, 1120))
        headline(base, t, 18.3, 19.7, "RIP. WIPE. WASH. REPEAT.", 1440, 110, TEAL)

    # F: end card
    k = win(t, 19.6, DUR + 1, 0.45, 0.1)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 120, "HSW365", M(44), ACC)
        ctext(ld, 176, "TEAR-OFF MICROFIBER ROLL", B(104), WHITE)
        ctext(ld, 310, "30 sheets  ·  wash + reuse  ·  lint-free", I("InterDisplay-Medium.otf", 42), (210, 210, 222))
        ctext(ld, 372, "$10.99", B(150), GOLD)
        lay.alpha_composite(QR2, ((W - QR2.width) // 2, 580))
        ctext(ld, 1030, "SCAN TO SUBSCRIBE", B(84), CYAN)
        ctext(ld, 1140, "hsw365.co", M(52), WHITE)
        ctext(ld, 1214, "Kitchen  ·  Car  ·  Glass  ·  Garage", I("Inter-Medium.otf", 36), MUT)
        ctext(ld, 1720, "HSW365  ·  Turn Negative Into Positive", I("Inter-Medium.otf", 30), (120, 120, 140))
        paste(base, lay, k, (0, 20 * (1 - k)))

    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < 0.4: arr *= clamp(t / 0.4)
    if t > DUR - 0.4: arr *= clamp((DUR - t) / 0.4)
    for tc in CUTS:
        if 0 <= t - tc < 0.12: arr = arr * 0.6 + 255 * 0.4 * (1 - (t - tc) / 0.12)
    return finish(arr, i)


def mybubble_(text):
    font = I("Inter-Regular.otf", 44); lines = wrap(text, font, 700); lh = int(font.size * 1.28)
    bw = int(max(tw(font, l) for l in lines)) + 60; bh = lh * len(lines) + 40
    b = rrect((bw, bh), 34, (*TEAL, 255)); d = ImageDraw.Draw(b)
    for i, l in enumerate(lines): d.text((30, 18 + i * lh), l, font=font, fill=(255, 255, 255))
    return b


def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr; a = np.zeros(n)
    def note(t0, f, dur, amp):
        i0 = int(t0 * sr); m = int(dur * sr); x = np.arange(m) / sr
        if i0 + m < n:
            a[i0:i0 + m] += amp * (np.sin(2 * np.pi * f * x) + 0.35 * np.sin(4 * np.pi * f * x) + 0.12 * np.sin(6 * np.pi * f * x)) * np.exp(-x * 2.2) * np.clip(x / 0.01, 0, 1)
    def noise(t0, dur, amp, decay):
        i0 = int(t0 * sr); m = int(dur * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += amp * rng.normal(0, 1, m) * np.exp(-x * decay)
    # light morning keys 0-4
    for c, ch in enumerate([(261.6, 329.6, 392.0), (293.7, 349.2, 440.0)]):
        for f in ch: note(0.3 + c * 1.0, f, 1.2, 0.04)
    # glass clink + splash
    for f in (2093.0, 2637.0): note(1.35, f, 0.4, 0.07)
    noise(1.55, 0.9, 0.16, 4.5)
    # record scratch / sad trombone-ish drop at the empty roll
    i0 = int(4.4 * sr); m = int(0.7 * sr); x = np.arange(m) / sr
    a[i0:i0 + m] += 0.12 * np.sin(2 * np.pi * (300 - 220 * x / 0.7) * x) * np.exp(-x * 2)
    # receipt printer ticks
    for ts in (5.7, 6.3, 6.9, 7.3): noise(ts, 0.08, 0.08, 60)
    # text pops
    for p_ in (8.15, 8.85, 9.65, 10.45):
        i0 = int(p_ * sr); m = int(0.09 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.18 * np.sin(2 * np.pi * (950 - 3000 * x) * x) * np.exp(-x * 45)
    # the RIP
    noise(11.95, 0.45, 0.32, 9)
    # beat from 11.4 at 100 bpm
    spb = 60 / 100
    def kick(t0):
        i0 = int(t0 * sr); m = int(0.35 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += 0.6 * np.sin(2 * np.pi * (110 * np.exp(-x * 20) + 45) * x) * np.exp(-x * 7)
    def snare(t0):
        i0 = int(t0 * sr); m = int(0.22 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += (0.2 * rng.normal(0, 1, m) + 0.2 * np.sin(2 * np.pi * 190 * x)) * np.exp(-x * 20)
    prog = [(174.6, 220.0, 261.6), (196.0, 246.9, 293.7), (220.0, 261.6, 329.6), (196.0, 246.9, 293.7)]
    beat = 0; tb = 11.4
    while tb < DUR - 0.6:
        if beat % 4 == 0 or beat % 8 == 5: kick(tb)
        if beat % 4 == 2: snare(tb)
        noise(tb + spb / 2, 0.05, 0.05, 80); noise(tb, 0.05, 0.03, 80)
        if beat % 4 == 0:
            ch = prog[(beat // 4) % 4]
            for f in ch: note(tb, f, spb * 4, 0.035)
            note(tb, ch[0] / 2, spb * 3.5, 0.11)
        tb += spb; beat += 1
    # wipe swish
    noise(13.6, 1.4, 0.06, 1.2)
    for tc in CUTS:
        i0 = int((tc - 0.25) * sr); m = int(0.5 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.12 * np.convolve(rng.normal(0, 1, m), np.ones(12) / 12, "same") * np.sin(np.pi * x / 0.5) ** 2
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
