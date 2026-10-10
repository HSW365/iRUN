"""Faceless video maker: script scenes -> AI image per scene -> voiceover -> word-by-word captions -> MP4.

A faceless script looks like:
{
  "title": "Your setback is the setup",
  "scenes": [{"say": "one spoken line", "visual": "what the picture shows"}, ...],   # 5-10 scenes
  "caption": "post caption", "hashtags": ["tag", ...]
}
Output is 1080x1920, 30fps, H.264 + AAC: slow camera moves over each image, crossfades between scenes,
big captions that light up word by word, and a call-to-action card at the end.
"""
import os
import random
import re
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFont

import visuals
import voice

W, H, FPS = 1080, 1920, 30
CYAN, VIOLET, RED, YELLOW, WHITE, MUTED = (34, 211, 238), (168, 85, 247), (239, 68, 68), (251, 191, 36), \
    (242, 242, 247), (170, 170, 190)
FONTS = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
OVER = 1.2          # scene images are held 20% larger than the frame so the camera has room to move
GAP = 0.22          # pause between scenes (seconds)
XF = 0.35           # crossfade between scenes
TAIL = 2.0          # call-to-action card after the last line
CAP_Y = int(H * 0.60)


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def clean(script):
    """Validate and tidy a faceless script. Raises ValueError when it can't be used."""
    scenes = []
    for s in script.get("scenes", []):
        say = re.sub(r"[^\x00-\x7F]+", "", str(s.get("say", ""))).strip()
        vis = str(s.get("visual", "")).strip()
        if say and vis:
            scenes.append({"say": say, "visual": vis})
    if not 4 <= len(scenes) <= 12:
        raise ValueError(f"needs 4-12 scenes with 'say' and 'visual', got {len(scenes)}")
    tags = [str(t).lstrip("#").replace(" ", "") for t in script.get("hashtags", [])][:6]
    return {"title": str(script.get("title") or scenes[0]["say"]).strip(), "scenes": scenes,
            "caption": str(script.get("caption", "")).strip(), "hashtags": tags,
            "style": script.get("style")}


# ---------- captions ----------

def chunks(words, marks, max_words=3, max_chars=16):
    """Group words into short caption cards. Returns [{"words": [...], "marks": [(s, e)...]}]."""
    out, cur, curm = [], [], []
    for w, m in zip(words, marks):
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            out.append({"words": cur, "marks": curm})
            cur, curm = [], []
        cur.append(w)
        curm.append(m)
        if re.search(r"[.!?,;:]$", w):
            out.append({"words": cur, "marks": curm})
            cur, curm = [], []
    if cur:
        out.append({"words": cur, "marks": curm})
    return out


class Captions:
    """Pre-draws each caption card once per highlighted word, so per-frame work is a paste."""

    def __init__(self):
        self.cache = {}
        self.scratch = ImageDraw.Draw(Image.new("RGB", (8, 8)))

    def sprite(self, words, active):
        key = (tuple(words), active)
        if key in self.cache:
            return self.cache[key]
        up = [re.sub(r"[.,;:]+$", "", w).upper() for w in words]
        size = 138
        while True:
            font = _font("BarlowCondensed-ExtraBold.ttf", size)
            space = self.scratch.textlength(" ", font=font)
            widths = [self.scratch.textlength(w, font=font) for w in up]
            lines, line, lw = [], [], 0
            for i, wd in enumerate(widths):
                if line and lw + space + wd > 900:
                    lines.append(line)
                    line, lw = [], 0
                lw += wd + (space if line else 0)
                line.append(i)
            lines.append(line)
            if (len(lines) <= 2 and max(widths) <= 900) or size <= 80:
                break
            size -= 10
        stroke, lh = max(size // 11, 8), int(size * 1.06)
        img = Image.new("RGBA", (W, lh * len(lines) + 2 * stroke + 20), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y = stroke
        for line in lines:
            total = sum(widths[i] for i in line) + space * (len(line) - 1)
            x = (W - total) / 2
            for i in line:
                d.text((x + 5, y + 7), up[i], font=font, fill=(0, 0, 0, 150), stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
                x += widths[i] + space
            x = (W - total) / 2
            for i in line:
                d.text((x, y), up[i], font=font, fill=YELLOW if i == active else WHITE,
                       stroke_width=stroke, stroke_fill=(8, 8, 12))
                x += widths[i] + space
            y += lh
        self.cache[key] = img
        return img


# ---------- frame pieces ----------

def _cover(path):
    img = Image.open(path).convert("RGB")
    tw, th = int(W * OVER), int(H * OVER)
    s = max(tw / img.width, th / img.height)
    img = img.resize((max(tw, round(img.width * s)), max(th, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((x, y, x + tw, y + th))


MOVES = ["in", "out", "left", "right", "up"]


def _camera(img, move, p):
    """One frame of a slow camera move over an oversized image. p runs 0..1 across the scene."""
    p = min(max(p, 0.0), 1.0)
    sw, sh = img.size
    z0, z1 = {"in": (1.02, 1.16), "out": (1.16, 1.02)}.get(move, (1.10, 1.10))
    z = z0 + (z1 - z0) * p
    bw, bh = sw / z, sh / z
    cx, cy = sw / 2, sh / 2
    slack_x, slack_y = (sw - bw) / 2, (sh - bh) / 2
    if move == "left":
        cx += slack_x * (0.9 - 1.8 * p)
    elif move == "right":
        cx -= slack_x * (0.9 - 1.8 * p)
    elif move == "up":
        cy += slack_y * (0.9 - 1.8 * p)
    box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    return img.transform((W, H), Image.EXTENT, box, Image.BILINEAR)


def _shade():
    """Multiply layer: darker at the top (brand tag) and through the caption band so text always reads."""
    col = Image.new("L", (1, H))
    px = col.load()
    for y in range(H):
        t = y / H
        v = 0.90
        if t < 0.18:
            v = 0.62 + 0.28 * (t / 0.18)
        elif t > 0.42:
            v = 0.90 - 0.34 * min((t - 0.42) / 0.22, 1.0)
        px[0, y] = int(255 * v)
    return Image.merge("RGB", [col.resize((W, H))] * 3)


def _brand(handle, series_name):
    img = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mono = _font("SpaceMono-Bold.ttf", 30)
    for dx, dy, fill in ((2, 3, (0, 0, 0, 170)), (0, 0, None)):
        d.text((70 + dx, 150 + dy), "@" + handle.upper(), font=mono, fill=fill or CYAN)
        tw = d.textlength(series_name, font=mono)
        if tw <= W - 140 - d.textlength("@" + handle.upper() + "   ", font=mono):
            d.text((W - 70 - tw + dx, 150 + dy), series_name, font=mono, fill=fill or WHITE)
    d.rectangle([70, 205, 190, 211], fill=VIOLET)
    return img


def _cta_card(cta):
    label, sub = cta
    img = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 96
    while True:
        pill = _font("BarlowCondensed-ExtraBold.ttf", size)
        tw = d.textlength(label, font=pill)
        if tw <= W - 240 or size <= 56:
            break
        size -= 6
    bw, bh = tw + 100, int(size * 1.55)
    bx = (W - bw) / 2
    d.rounded_rectangle([bx, 40, bx + bw, 40 + bh], radius=22, fill=RED)
    d.text((bx + 50, 40 + (bh - size * 1.18) / 2), label, font=pill, fill=WHITE)
    mono = _font("SpaceMono-Bold.ttf", 32)
    sw = d.textlength(sub, font=mono)
    if sw > W - 140:
        mono = _font("SpaceMono-Bold.ttf", 24)
        sw = d.textlength(sub, font=mono)
    d.text(((W - sw) / 2 + 2, 40 + bh + 43), sub, font=mono, fill=(0, 0, 0, 200))
    d.text(((W - sw) / 2, 40 + bh + 40), sub, font=mono, fill=WHITE)
    return img


def _fade(img, a):
    if a >= 0.999:
        return img
    alpha = img.getchannel("A").point(lambda v: int(v * a))
    out = img.copy()
    out.putalpha(alpha)
    return out


# ---------- build ----------

def build(script, style_id, workdir, out_path, cta, handle, series_name, seed=None):
    """Make the video. Returns {"voice", "seconds", "media": [{"visual", "source"}], "images": [paths]}."""
    scenes = script["scenes"]
    seed = seed if seed is not None else random.randrange(1, 10**6)
    rnd = random.Random(seed)

    # 1. voice + word timings, one clip per scene
    clips, t = [], 0.0
    vsrc = "edge-tts"
    for i, sc in enumerate(scenes):
        mp3 = os.path.join(workdir, f"v{i}.mp3")
        _, length, vsrc, marks = voice.speak_timed(sc["say"], mp3)
        clips.append({"mp3": mp3, "start": t, "len": length, "marks": marks})
        t += length + GAP
    total = t - GAP + TAIL
    for i, c in enumerate(clips):  # each scene runs until the next one starts
        c["end"] = clips[i + 1]["start"] if i + 1 < len(clips) else total

    # 2. one audio track: clips back to back with the pause between them
    ins, parts = [], []
    for i, c in enumerate(clips):
        ins += ["-i", c["mp3"]]
        parts.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono,apad=whole_dur={c['len'] + GAP:.3f}[a{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(len(clips))) + \
        f"concat=n={len(clips)}:v=0:a=1,apad=whole_dur={total:.3f}[a]"
    wav = os.path.join(workdir, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", graph, "-map", "[a]",
                    "-t", f"{total:.3f}", wav], check=True)

    # 3. an image per scene
    media, images, moves = [], [], []
    last = None
    for i, sc in enumerate(scenes):
        path, source = visuals.scene_image(sc["visual"], style_id, seed * 100 + i, os.path.join(workdir, f"img{i}.jpg"))
        media.append({"visual": sc["visual"], "source": source})
        images.append(path)
        move = rnd.choice([m for m in MOVES if m != last])
        moves.append(move)
        last = move
    pics = [_cover(p) for p in images]

    # 4. caption cards on the timeline
    cards = []
    for sc, c in zip(scenes, clips):
        for ch in chunks(sc["say"].split(), c["marks"]):
            cards.append({"words": ch["words"], "start": c["start"] + ch["marks"][0][0],
                          "marks": [(c["start"] + s, c["start"] + e) for s, e in ch["marks"]],
                          "scene_end": c["start"] + c["len"] + 0.12})
    for a, b in zip(cards, cards[1:]):
        a["end"] = min(b["start"], a["scene_end"])
    cards[-1]["end"] = cards[-1]["scene_end"]

    caps, shade, brand, card = Captions(), _shade(), _brand(handle, series_name), _cta_card(cta)
    speech_end = clips[-1]["start"] + clips[-1]["len"]
    n = int(total * FPS)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", "-movflags", "+faststart",
         out_path], stdin=subprocess.PIPE)
    ci = 0
    for f in range(n):
        now = f / FPS
        si = max(i for i, c in enumerate(clips) if now >= c["start"] or i == 0)
        c = clips[si]
        span = c["end"] - c["start"] + XF
        frame = _camera(pics[si], moves[si], (now - c["start"]) / span)
        if si and now - c["start"] < XF:  # crossfade from the scene before, which keeps moving
            p = clips[si - 1]
            prev = _camera(pics[si - 1], moves[si - 1], (now - p["start"]) / (p["end"] - p["start"] + XF))
            frame = Image.blend(prev, frame, (now - c["start"]) / XF)
        frame = ImageChops.multiply(frame, shade)
        frame.paste(brand, (0, 0), brand)

        while ci + 1 < len(cards) and now >= cards[ci + 1]["start"]:
            ci += 1
        cd = cards[ci]
        if cd["start"] <= now < cd["end"] and now < speech_end + 0.12:
            active = max([k for k, (s, _) in enumerate(cd["marks"]) if now >= s], default=0)
            sp = caps.sprite(cd["words"], active)
            pop = min((now - cd["start"]) / 0.10, 1.0)
            if pop < 1.0:
                sc_ = 0.86 + 0.14 * pop
                sp = sp.resize((int(sp.width * sc_), int(sp.height * sc_)), Image.BILINEAR)
            frame.paste(sp, ((W - sp.width) // 2, CAP_Y - sp.height // 2), sp)
        elif now >= speech_end + 0.15:
            a = min((now - speech_end - 0.15) / 0.3, 1.0)
            cc = _fade(card, a)
            frame.paste(cc, (0, CAP_Y - 150 + int((1 - a) * 30)), cc)

        d = ImageDraw.Draw(frame)
        d.rectangle([70, H - 420, W - 70, H - 415], fill=(30, 30, 42))
        d.rectangle([70, H - 420, 70 + int((W - 140) * (f + 1) / n), H - 415], fill=CYAN)
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding the faceless video")
    return {"voice": vsrc, "seconds": round(total, 1), "media": media, "images": images}
