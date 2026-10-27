"""HSW365 Ultimate Package micro-drama: "First To Answer" - 30s, 1080x1920, 30fps.
A roofer is up on a roof at 4:12 PM. His phone buzzes in his pocket. Three missed calls.
The voicemail: "calling three roofers, whoever calls back first gets it." By the time he
climbs down, somebody else got the job. His wife texts: no website, page dead since 2023.
QUEENEE builds the site, CallTwin catches every missed call and emails the job,
iRun posts his work every day. Next week the jobs come to him. QR to sign up.
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from queenee_render import *  # shared helpers: fonts, gradients, bubble, phone, rrect, wrap, etc.
import queenee_render as Q

ORANGE = (249, 115, 22); GREEN = (34, 197, 94)
ACC = ORANGE
Q.RED = ORANGE
URL = "https://hsw365.github.io/queenee/?src=pkg-ad#signup"
DUSK = vgrad((20, 12, 10), (40, 20, 14))
NIGHT2 = vgrad((6, 7, 14), (14, 12, 22))
ACCGLOW = np.exp(-(((xx - W * 0.5) / (W * 0.6)) ** 2 + ((yy - H * 0.4) / (H * 0.32)) ** 2))[..., None].astype(np.float32)

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

def mybubble(text):
    font = I("Inter-Regular.otf", 44); lines = wrap(text, font, 700); lh = int(font.size * 1.28)
    bw = int(max(tw(font, l) for l in lines)) + 60; bh = lh * len(lines) + 40
    b = rrect((bw, bh), 34, (*ACC, 255)); d = ImageDraw.Draw(b)
    for i, l in enumerate(lines): d.text((30, 18 + i * lh), l, font=font, fill=(255, 255, 255))
    return b

# ---------- missed call card ----------
def missed_card(n_calls):
    c = rrect((W - 120, 150), 34, (24, 24, 34, 245), (*LINE, 255)); d = ImageDraw.Draw(c)
    ic = rrect((90, 90), 22, (*RED_, 255)); ImageDraw.Draw(ic).text((45 - tw(B(60), "!") / 2, 6), "!", font=B(60), fill=WHITE)
    c.alpha_composite(ic, (30, 30))
    d.text((144, 28), "PHONE", font=M(24), fill=RED_)
    d.text((144, 62), f"{n_calls} Missed Call{'s' if n_calls > 1 else ''}", font=I("Inter-SemiBold.otf", 40), fill=WHITE)
    d.text((W - 150 - tw(I("Inter-Regular.otf", 26), "now"), 30), "now", font=I("Inter-Regular.otf", 26), fill=MUT)
    return c
RED_ = (239, 68, 68)

def voicemail_card(prog):
    cw = W - 120
    c = rrect((cw, 520), 40, (*CARD, 255), (*LINE, 255)); d = ImageDraw.Draw(c)
    d.text((50, 44), "VOICEMAIL  ·  (216) 555-0148", font=M(28), fill=MUT)
    d.text((50, 92), "4:13 PM  ·  0:11", font=I("Inter-Medium.otf", 34), fill=(200, 200, 214))
    for k in range(40):
        hgt = 10 + 44 * abs(math.sin(k * 0.7)) * (0.5 + 0.5 * abs(math.cos(k * 0.31)))
        col = (*ACC, 255) if k / 40 < prog else (70, 70, 84, 255)
        d.rounded_rectangle((50 + k * 21, 200 - hgt / 2, 62 + k * 21, 200 + hgt / 2), 4, fill=col)
    txt = "\"Hey, roof's leaking bad. I'm calling three roofers. Whoever calls me back first gets the job.\""
    f = I("InterDisplay-Medium.otf", 40)
    shown = txt[: int(len(txt) * clamp(prog * 1.15))]
    for i, ln in enumerate(wrap(shown, f, cw - 100)):
        d.text((50, 270 + i * 54), ln, font=f, fill=WHITE)
    return c

# ---------- CallTwin email alert ----------
def email_card(name, job, addr, phone_):
    cw = W - 120
    c = rrect((cw, 300), 34, (24, 24, 34, 245), (*LINE, 255)); d = ImageDraw.Draw(c)
    ic = rrect((90, 90), 22, (*CYAN, 255)); ImageDraw.Draw(ic).text((45 - tw(B(52), "CT") / 2, 12), "CT", font=B(52), fill=INK)
    c.alpha_composite(ic, (30, 30))
    d.text((144, 26), "CALLTWIN  ·  NEW JOB", font=M(24), fill=CYAN)
    d.text((144, 62), name, font=I("Inter-SemiBold.otf", 40), fill=WHITE)
    d.text((W - 150 - tw(I("Inter-Regular.otf", 26), "now"), 28), "now", font=I("Inter-Regular.otf", 26), fill=MUT)
    d.text((40, 150), job, font=I("Inter-SemiBold.otf", 34), fill=(230, 230, 240))
    d.text((40, 198), addr, font=I("Inter-Regular.otf", 30), fill=(190, 190, 204))
    d.text((40, 244), phone_, font=M(28), fill=GOLD)
    return c

# ---------- the three pieces ----------
def piece_card(tag, name, line, col, icon):
    cw = W - 120
    c = rrect((cw, 250), 40, (*CARD, 255), (*col, 255), 3); d = ImageDraw.Draw(c)
    ic = rrect((140, 140), 32, (*col, 255)); ImageDraw.Draw(ic).text((70 - tw(B(80), icon) / 2, 18), icon, font=B(80), fill=INK)
    c.alpha_composite(ic, (40, 55))
    d.text((210, 52), tag, font=M(26), fill=col)
    d.text((206, 86), name, font=B(84), fill=WHITE)
    d.text((210, 184), line, font=I("Inter-Medium.otf", 32), fill=(200, 200, 214))
    return c
PIECES = [("THE WEBSITE", "QUEENEE", "Your site, on your own domain", ACC, "Q"),
          ("THE PHONE", "CALLTWIN", "Every missed call emailed to you", CYAN, "CT"),
          ("THE SOCIALS", "iRUN", "Your work posted every single day", GOLD, "iR")]

def ig_post():
    pw = W - 240
    c = rrect((pw, 300), 30, (24, 24, 34, 245), (*LINE, 255)); d = ImageDraw.Draw(c)
    ic = rrect((84, 84), 42, (*GOLD, 255)); ImageDraw.Draw(ic).text((42 - tw(B(46), "iR") / 2, 14), "iR", font=B(46), fill=INK)
    c.alpha_composite(ic, (28, 28))
    d.text((128, 30), "INSTAGRAM  ·  NEW DM", font=M(24), fill=GOLD)
    d.text((128, 64), "@kel.homes", font=I("Inter-SemiBold.otf", 38), fill=WHITE)
    f = I("Inter-Regular.otf", 32)
    for i, ln in enumerate(wrap("\"saw your tear-off video. can you do mine next week?\"", f, pw - 70)):
        d.text((32, 150 + i * 44), ln, font=f, fill=(210, 210, 222))
    return c

def qr_card2(box=420):
    import segno
    buf = io.BytesIO(); segno.make(URL, error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
    code = Image.open(buf).convert("RGBA").resize((box - 60, box - 60), Image.NEAREST)
    c = rrect((box, box), 36, (255, 255, 255, 255)); c.alpha_composite(code, (30, 30))
    badge = rrect((96, 96), 22, (*ACC, 255)); bd = ImageDraw.Draw(badge)
    bf = B(56); bd.text(((96 - tw(bf, "HSW")) / 2, 14), "HSW", font=bf, fill=WHITE)
    wb = rrect((112, 112), 26, (255, 255, 255, 255)); wb.alpha_composite(badge, (8, 8))
    c.alpha_composite(wb, ((box - 112) // 2, (box - 112) // 2))
    return c
QR2 = qr_card2()

CUTS = (4.0, 9.2, 12.8, 16.4, 22.6, 26.4)
def frame(i):
    t = i / FPS
    if t < 12.8: bg = DUSK * (1 - clamp((t - 8) / 4) * 0.6) + NIGHT2 * clamp((t - 8) / 4) * 0.6
    elif t < 26.4: bg = NIGHT2 + ACCGLOW * np.array([60, 26, 8], np.float32) * win(t, 12.8, 26.4, 0.6, 0.6)
    else: bg = NIGHT2 * 0.8 + DUSK * 0.2
    base = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")

    # A: on the roof, phone keeps buzzing
    k = win(t, 0.2, 4.1, 0.6, 0.35)
    if k:
        lay = Image.new("RGBA", (W, 560), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "Up on a roof. Hands full.", I("Inter-Medium.otf", 44), MUT)
        ctext(ld, 60, "4:12", I("InterDisplay-Thin.otf", 300), WHITE)
        paste(base, lay, k, (0, 330))
        for n in range(3):
            ts = 1.0 + n * 0.8
            if t >= ts:
                a = ease((t - ts) / 0.25)
                shake = 6 * math.sin(t * 90) * clamp(1 - (t - ts) / 0.4)
                paste(base, missed_card(n + 1), a * k, (60 + shake, 860 + n * 0 - 30 * (1 - a)))
        caption(base, t, 1.6, 4.1, "Bzzz. Bzzz. Bzzz.", 1120, I("InterDisplay-SemiBold.otf", 60), (210, 210, 222))

    # B: voicemail
    k = win(t, 4.0, 9.3, 0.4, 0.35)
    if k:
        card = voicemail_card(clamp((t - 4.3) / 3.4))
        paste(base, card, k, (60, 380 - 20 * (1 - k)))
        headline(base, t, 7.6, 9.3, "HE CALLED BACK AT 5:40.", 1060, 104, WHITE)
        caption(base, t, 8.1, 9.3, "\"Sorry man, somebody already answered.\"", 1230, I("InterDisplay-Medium.otf", 50), RED_)

    # C: wife texts
    k = win(t, 9.2, 12.9, 0.3, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(chat_header2("Tasha", "wife", "6:02"), (0, 0))
        msgs = [(bubble("that's the 4th job this month babe", False), 9.35, False),
                (bubble("people google you and find NOTHING. your page ain't posted since 2023", False), 10.05, False),
                (mybubble("I can't run a roof and a phone and a page"), 10.95, True),
                (bubble("then stop doing it yourself", False), 11.75, False)]
        y = 290
        for bb, ts, mine in msgs:
            if t >= ts:
                a = ease((t - ts) / 0.22); x = W - 60 - bb.width if mine else 60
                lay.alpha_composite(alpha(bb, a), (int(x), int(y + 20 * (1 - a))))
            y += bb.height + 26
        paste(base, lay, k)

    # D: the three pieces
    k = win(t, 12.8, 16.5, 0.35, 0.3)
    if k:
        lay = Image.new("RGBA", (W, 220), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 0, "HSW365 MEDIA SET HIM UP WITH", M(30), MUT)
        ctext(ld, 44, "ALL THREE", B(124), WHITE)
        paste(base, lay, k, (0, 200))
        for n, pc in enumerate(PIECES):
            ts = 13.2 + n * 0.75
            if t >= ts:
                a = ease((t - ts) / 0.3)
                paste(base, piece_card(*pc), a * k, (60 + 60 * (1 - a), 480 + n * 290))
        caption(base, t, 15.4, 16.5, "He just does roofs.", 1420, I("InterDisplay-SemiBold.otf", 62))

    # E: next missed call -> CallTwin emails the job; DM lead; site request
    k = win(t, 16.4, 22.7, 0.3, 0.35)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 140, "Next Tuesday · still on a roof", I("Inter-Medium.otf", 40), MUT)
        ctext(ld, 190, "2:31", I("InterDisplay-Thin.otf", 200), WHITE)
        items = [(missed_card(1), 16.8),
                 (email_card("Dana Ruiz", "Roof leak over kitchen — needs estimate", "18 Elm Ct, Parma OH", "Call back: (216) 555-0172"), 17.6),
                 (ig_post(), 18.9)]
        y = 470
        for c, ts in items:
            if t >= ts:
                a = ease((t - ts) / 0.25)
                lay.alpha_composite(alpha(c, a), ((W - c.width) // 2, int(y - 40 * (1 - a))))
            y += c.height + 30
        paste(base, lay, k)
        headline(base, t, 20.4, 22.7, "HE CALLS BACK FIRST.", 1500, 120, ACC)
        caption(base, t, 21.0, 22.7, "Name. Number. Job. Already in his email.", 1660, I("InterDisplay-Medium.otf", 44), (210, 210, 222))

    # F: the turn
    k = win(t, 22.6, 26.5, 0.3, 0.3)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        lay.alpha_composite(chat_header2("Tasha", "wife", "7:15"), (0, 0))
        msgs = [(mybubble("booked 3 jobs this week. didn't touch my phone once"), 22.8, True),
                (bubble("who's posting your videos??", False), 23.7, False),
                (mybubble("iRun. I just roof"), 24.5, True)]
        y = 290
        for bb, ts, mine in msgs:
            if t >= ts:
                a = ease((t - ts) / 0.22); x = W - 60 - bb.width if mine else 60
                lay.alpha_composite(alpha(bb, a), (int(x), int(y + 20 * (1 - a))))
            y += bb.height + 26
        paste(base, lay, k)
        headline(base, t, 25.0, 26.5, "STOP LOSING JOBS.", 1300, 130, WHITE)

    # G: end card
    k = win(t, 26.4, 31, 0.45, 0.1)
    if k:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        ctext(ld, 140, "HSW365 MEDIA", M(44), ACC)
        ctext(ld, 195, "THE ULTIMATE PACKAGE", B(118), WHITE)
        ctext(ld, 350, "QUEENEE  ·  CALLTWIN  ·  iRUN", M(40), (210, 210, 222))
        ctext(ld, 410, "Website. Phone. Socials. Handled.", I("InterDisplay-Medium.otf", 46), (210, 210, 222))
        lay.alpha_composite(QR2, ((W - QR2.width) // 2, 520))
        ctext(ld, 975, "SCAN TO SUBSCRIBE", B(80), CYAN)
        pills = ["Contractors", "Shops", "Anyone"]
        pw = 290; gx = (W - pw * 3 - 30) // 2
        for n, p_ in enumerate(pills):
            c = rrect((pw, 84), 42, (*CARD, 255), (*(ACC if n == 0 else LINE), 255), 3)
            ctext(ImageDraw.Draw(c), 22, p_, I("Inter-SemiBold.otf", 34), WHITE, 0, pw)
            lay.alpha_composite(c, (gx + n * (pw + 15), 1100))
        ctext(ld, 1260, "hsw365.co", M(48), WHITE)
        ctext(ld, 1330, "Free mockup before you pay a dime", I("Inter-Medium.otf", 34), MUT)
        ctext(ld, 1720, "HSW365 Media  ·  Turn Negative Into Positive", I("Inter-Medium.otf", 30), (120, 120, 140))
        paste(base, lay, k, (0, 20 * (1 - k)))

    arr = np.asarray(base.convert("RGB")).astype(np.float32)
    if t < 0.5: arr *= clamp(t / 0.5)
    if t > 29.6: arr *= clamp((30 - t) / 0.4)
    for tc in CUTS:
        if 0 <= t - tc < 0.12: arr = arr * 0.6 + 255 * 0.4 * (1 - (t - tc) / 0.12)
    return finish(arr, i)

def audio(path):
    sr = 44100; n = int(sr * DUR); tt = np.arange(n) / sr; a = np.zeros(n)
    def note(t0, f, dur, amp):
        i0 = int(t0 * sr); m = int(dur * sr); x = np.arange(m) / sr
        if i0 + m < n:
            a[i0:i0 + m] += amp * (np.sin(2 * np.pi * f * x) + 0.35 * np.sin(4 * np.pi * f * x) + 0.12 * np.sin(6 * np.pi * f * x)) * np.exp(-x * 2.2) * np.clip(x / 0.01, 0, 1)
    # tense low pad 0-12.8
    chords = [(146.8, 174.6, 220.0), (130.8, 164.8, 196.0), (116.5, 146.8, 174.6), (110.0, 138.6, 164.8)]
    for c in range(4):
        for f in chords[c]: note(0.3 + c * 3.1, f, 3.0, 0.05)
    a += 0.035 * np.sin(2 * np.pi * 49 * tt) * np.clip(tt / 1.5, 0, 1) * np.clip((12.8 - tt) / 0.6, 0, 1)
    # phone buzzes
    for ts in (1.0, 1.8, 2.6):
        i0 = int(ts * sr); m = int(0.35 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.18 * np.sign(np.sin(2 * np.pi * 150 * x)) * (np.sin(2 * np.pi * 12 * x) > 0) * np.exp(-x * 3)
    # beat from 12.8 at 92 bpm
    spb = 60 / 92
    def kick(t0):
        i0 = int(t0 * sr); m = int(0.35 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += 0.6 * np.sin(2 * np.pi * (110 * np.exp(-x * 20) + 45) * x) * np.exp(-x * 7)
    def hat(t0, amp=0.05):
        i0 = int(t0 * sr); m = int(0.05 * sr)
        if i0 + m < n: a[i0:i0 + m] += amp * rng.normal(0, 1, m) * np.exp(-np.arange(m) / sr * 80)
    def snare(t0):
        i0 = int(t0 * sr); m = int(0.22 * sr); x = np.arange(m) / sr
        if i0 + m < n: a[i0:i0 + m] += (0.2 * rng.normal(0, 1, m) + 0.2 * np.sin(2 * np.pi * 190 * x)) * np.exp(-x * 20)
    prog = [(146.8, 185.0, 220.0), (130.8, 164.8, 196.0), (174.6, 220.0, 261.6), (164.8, 207.7, 246.9)]
    beat = 0; tb = 12.8
    while tb < 29.3:
        if beat % 4 == 0 or beat % 8 == 5: kick(tb)
        if beat % 4 == 2: snare(tb)
        hat(tb + spb / 2); hat(tb, 0.03)
        if beat % 4 == 0:
            ch = prog[(beat // 4) % 4]
            for f in ch: note(tb, f, spb * 4, 0.035)
            note(tb, ch[0] / 2, spb * 3.5, 0.11)
        tb += spb; beat += 1
    for tc in CUTS:
        i0 = int((tc - 0.25) * sr); m = int(0.5 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.12 * np.convolve(rng.normal(0, 1, m), np.ones(12) / 12, "same") * np.sin(np.pi * x / 0.5) ** 2
    for p_ in (9.35, 10.05, 10.95, 11.75, 22.8, 23.7, 24.5):
        i0 = int(p_ * sr); m = int(0.09 * sr); x = np.arange(m) / sr
        a[i0:i0 + m] += 0.18 * np.sin(2 * np.pi * (950 - 3000 * x) * x) * np.exp(-x * 45)
    for t0 in (17.6, 18.9):
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
