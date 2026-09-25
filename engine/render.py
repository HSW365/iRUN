"""Renderer: HSW365 dark-premium kinetic text video, 1080x1920, 30fps, H.264 + AAC."""
import os
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
BASE = (10, 10, 15)
CYAN = (34, 211, 238)
VIOLET = (168, 85, 247)
RED = (239, 68, 68)
YELLOW = (251, 191, 36)
WHITE = (242, 242, 247)
MUTED = (120, 120, 140)
FONTS = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _background(i, n):
    img = Image.new("RGB", (W, H), BASE)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    t = i / max(n - 1, 1)
    cx1, cy1 = int(W * (0.15 + 0.5 * t)), int(H * 0.28)
    cx2, cy2 = int(W * (0.85 - 0.4 * t)), int(H * 0.72)
    d.ellipse([cx1 - 520, cy1 - 520, cx1 + 520, cy1 + 520], fill=(14, 70, 84))
    d.ellipse([cx2 - 560, cy2 - 560, cx2 + 560, cy2 + 560], fill=(62, 26, 92))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.blend(img, glow, 0.55)
    g = ImageDraw.Draw(img)
    for x in range(0, W, 90):
        g.line([(x, 0), (x, H)], fill=(18, 18, 26), width=1)
    for y in range(0, H, 90):
        g.line([(0, y), (W, y)], fill=(18, 18, 26), width=1)
    return img


def _wrap(words, font, draw, max_w):
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if cur and draw.textlength(test, font=font) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def frame(text, emphasis, i, n, product_name, keyword, out, cta=None):
    img = _background(i, n)
    d = ImageDraw.Draw(img)
    mono = _font("SpaceMono-Bold.ttf", 30)
    d.text((70, 150), "HSW365 MEDIA", font=mono, fill=CYAN)
    tag = f"// {product_name}"
    d.text((W - 70 - d.textlength(tag, font=mono), 150), tag, font=mono, fill=MUTED)
    d.rectangle([70, 205, 190, 211], fill=VIOLET)

    last = i == n - 1
    words = text.upper().split()
    size = 150 if len(words) <= 5 else 128 if len(words) <= 7 else 112
    while True:
        font = _font("BarlowCondensed-ExtraBold.ttf", size)
        lines = _wrap(words, font, d, W - 180)
        if len(lines) <= 5 or size <= 84:
            break
        size -= 10
    lh = int(size * 1.02)
    block = lh * len(lines)
    y = int(H * 0.40) - block // 2
    emph = (emphasis or "").upper().strip(".,!?")
    kw = keyword.upper()
    for line in lines:
        x = 90
        for w in line:
            bare = w.strip(".,!?'\"")
            color = WHITE
            if bare == kw or (last and kw in bare):
                color = YELLOW
            elif emph and bare == emph:
                color = CYAN
            d.text((x, y), w, font=font, fill=color)
            x += d.textlength(w + " ", font=font)
        y += lh

    if last:
        pill = _font("BarlowCondensed-ExtraBold.ttf", 76)
        label, sub = cta or (f"COMMENT \"{kw}\"", "OR DM IT TO @HSW365MEDIA")
        tw = d.textlength(label, font=pill)
        bx, by = 90, y + 60
        d.rounded_rectangle([bx, by, bx + tw + 80, by + 120], radius=18, fill=RED)
        d.text((bx + 40, by + 14), label, font=pill, fill=WHITE)
        d.text((bx, by + 150), sub, font=mono, fill=MUTED)

    # progress
    d.rectangle([70, H - 420, W - 70, H - 414], fill=(30, 30, 42))
    d.rectangle([70, H - 420, 70 + int((W - 140) * (i + 1) / n), H - 414], fill=CYAN)
    img.save(out, "PNG")


def render(beats, emphasis, audio_path, audio_len, product, workdir, out_path, cta=None):
    n = len(beats)
    weights = [max(len(b.split()), 2) + 1.2 for b in beats]
    total = sum(weights)
    tail = 1.2
    durs = [audio_len * w / total for w in weights]
    durs[-1] += tail
    segs = []
    for i, (b, e, dur) in enumerate(zip(beats, emphasis, durs)):
        png = os.path.join(workdir, f"f{i}.png")
        frame(b, e, i, n, product["name"], product["keyword"], png, cta)
        seg = os.path.join(workdir, f"s{i}.mp4")
        frames = max(int(dur * 30), 15)
        zoom = f"zoompan=z='min(1+0.0009*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=30"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-vf",
             f"scale={int(W*1.15)}:-1,{zoom},format=yuv420p", "-frames:v", str(frames),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", seg],
            check=True,
        )
        segs.append(seg)
    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio_path,
         "-filter_complex", f"[1:a]apad=pad_dur={tail}[a]", "-map", "0:v", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", "-movflags", "+faststart", out_path],
        check=True,
    )
    return out_path
