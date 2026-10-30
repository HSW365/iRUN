"""Caption-box ad ("kind": "caption") — iRun's lo-fi POV style: real-looking handheld b-roll, then short lines that
stack one by one in black caption boxes (white rounded type), a narrator reading each line on its beat, and an end
beat with one CTA box + the scan-to-sign-up QR. Built to look like a real person's story, not a template promo.

  python engine/make_ad.py content/ads/<name>.json out/<name>-ad.mp4      (make_ad dispatches kind=caption here)

Spec:
{
  "kind": "caption", "name": "...", "link": "https://...signup",
  "lines": ["Line one", "Line two", "Line three", "Ask us anything"],
  "cta": "Scan to get started",
  "broll": {"file": "assets/ads/broll/x.mp4"}                         # or generate it:
           {"image": "still prompt", "motion": "camera move prompt", "seconds": 10},
  "vo": ["assets/voice/<slug>/vo1.wav", ...],   # one per line (+1 optional for the CTA); missing -> narrator.py makes them
  "say": ["what the narrator says per line", ...],                   # defaults to lines (+cta)
  "first_at": 0.9, "gap": 0.35, "hold": 1.2, "end": 3.6, "bed": "assets/audio/bed.mp3" (optional)
}
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
FONTS = os.path.join(ROOT, "assets", "fonts")
W, H, FPS = 1080, 1920, 30
BOX_TOP = 520          # first caption box top (matches the reference: upper-middle of frame)
BOX_GAP = 34
PAD_X, PAD_Y, RADIUS = 40, 26, 16
FONT_PX, MAX_W = 70, W - 60


def log(*a):
    print("[caption]", *a, flush=True)


def _p(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def _font(px):
    for name in ("ComicNeue-Bold.ttf", "BarlowCondensed-SemiBold.ttf"):
        try:
            return ImageFont.truetype(os.path.join(FONTS, name), px)
        except OSError:
            continue
    return ImageFont.load_default()


def _dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


# ---------- caption boxes ----------

def box_image(text, px=FONT_PX):
    """One black caption box with white rounded type; shrinks the type until it fits the frame width."""
    while True:
        f = _font(px)
        tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f)
        if tw + PAD_X * 2 <= MAX_W or px <= 40:
            break
        px -= 2
    asc, desc = f.getmetrics()
    w, h = int(tw + PAD_X * 2), int(asc + desc + PAD_Y * 2)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=RADIUS, fill=(0, 0, 0, 236))
    d.text((PAD_X, PAD_Y - 2), text, font=f, fill=(255, 255, 255, 255))
    return im


def layout(lines):
    """Stacked, centred boxes. Returns [(img, x, y)]."""
    boxes, y = [], BOX_TOP
    for t in lines:
        im = box_image(t)
        boxes.append((im, (W - im.width) // 2, y))
        y += im.height + BOX_GAP
    return boxes


def _pop(im, k):
    """Small pop-in: k in 0..1 -> scale 0.86 -> 1.03 -> 1.0 and fade in."""
    if k >= 1:
        return im
    s = 0.86 + 0.17 * min(1, k / 0.7) - 0.03 * max(0, (k - 0.7) / 0.3)
    a = min(1.0, k / 0.4)
    sm = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    if a < 1:
        alpha = sm.getchannel("A").point(lambda v: int(v * a))
        sm.putalpha(alpha)
    return sm


# ---------- b-roll ----------

def _ken(still, work, seconds):
    """Still -> handheld-looking clip (slow drift + micro shake) when no video model is available."""
    out = os.path.join(work, "broll_still.mp4")
    n = int(seconds * FPS)
    zp = (f"zoompan=z='1.08+0.06*on/{n}':x='iw/2-(iw/zoom/2)+18*sin(on/23)+on*0.35':"
          f"y='ih/2-(ih/zoom/2)+12*sin(on/17+1)':d={n}:s={W}x{H}:fps={FPS}")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", still, "-vf",
                    f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},{zp}",
                    "-t", f"{seconds:.2f}", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", out],
                   check=True)
    return out


def broll(spec, work, seconds):
    b = spec.get("broll") or {}
    if b.get("file") and os.path.exists(_p(b["file"])):
        return _p(b["file"]), "file"
    img_prompt = b.get("image") or "handheld phone photo, moody restaurant table, open laptop glowing, iced drink"
    seed = int(hashlib.sha1(img_prompt.encode()).hexdigest()[:6], 16)
    still = os.path.join(work, "broll.jpg")
    if os.environ.get("POLLINATIONS_TOKEN"):
        try:  # real motion b-roll: still frame -> image-to-video
            import movie
            url = movie.media_job("image", img_prompt, {"model": movie.IMAGE_MODEL, "width": W, "height": H,
                                                        "seed": seed}, still)
            if url:
                clip = os.path.join(work, "broll.mp4")
                for m in [movie.BROLL_MODEL] + movie.FALLBACK_VIDEO:
                    try:
                        movie.media_job("video", b.get("motion") or img_prompt,
                                        {"model": m, "image": url, "duration": int(b.get("seconds", 10)),
                                         "aspectRatio": "9:16", "resolution": "720p", "seed": seed}, clip)
                        if _dur(clip) > 1:
                            log("b-roll video", m)
                            return clip, m
                    except Exception as e:  # noqa: BLE001
                        log("video model failed", m, str(e)[:160])
        except Exception as e:  # noqa: BLE001
            log("b-roll generation failed", str(e)[:200])
    if not (os.path.exists(still) and os.path.getsize(still) > 1000):
        import visuals
        visuals.scene_image(img_prompt, "photoreal", seed, still, tries=4)
    return _ken(still, work, seconds), "still"


def _frames(path, n):
    """n frames at W x H from the b-roll, ping-ponged if it's shorter than the ad, with handheld micro-shake."""
    fw, fh = W + 60, H + 100
    work = tempfile.mkdtemp(prefix="irun-pp-")
    pp = os.path.join(work, "pp.mp4")  # forward + reverse at low res (bounded memory), looped to length below
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-filter_complex",
                    f"[0:v]fps={FPS},scale=-2:960,split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", pp], check=True)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", pp, "-frames:v", str(n), "-vf",
                             f"scale={fw}:{fh}:force_original_aspect_ratio=increase:flags=lanczos,crop={fw}:{fh},"
                             "eq=contrast=1.06:saturation=0.92:brightness=-0.02",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    t = np.arange(n)
    dx = (30 + 14 * np.sin(t / 19.0) + 6 * np.sin(t / 5.3)).astype(int)
    dy = (50 + 18 * np.sin(t / 23.0 + 1) + 7 * np.sin(t / 4.1)).astype(int)
    size, last = fw * fh * 3, None
    for i in range(n):
        buf = proc.stdout.read(size)
        if len(buf) == size:
            last = np.frombuffer(buf, np.uint8).reshape(fh, fw, 3)
        yield Image.fromarray(last[dy[i]:dy[i] + H, dx[i]:dx[i] + W])
    proc.stdout.close()
    proc.wait()


# ---------- audio ----------

def _wav_len(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def voices(spec, work):
    lines = list(spec["lines"]) + ([spec["cta"]] if spec.get("cta") else [])
    say = spec.get("say") or lines
    files = [_p(f) for f in spec.get("vo", [])]
    if len(files) >= len(spec["lines"]) and all(os.path.exists(f) for f in files):
        return files
    import narrator
    out = os.path.join(work, "vo")
    narrator.main(out, say)
    return [os.path.join(out, f"vo{i}.wav") for i in range(1, len(say) + 1)]


def timeline(spec, vos):
    t, starts = float(spec.get("first_at", 0.9)), []
    gap = float(spec.get("gap", 0.35))
    for i in range(len(spec["lines"])):
        starts.append(t)
        t += (_wav_len(vos[i]) if i < len(vos) else 1.4) + gap
    t += float(spec.get("hold", 0.6))
    cta_at = t
    end = t + max(float(spec.get("end", 3.6)), (_wav_len(vos[len(spec["lines"])]) + 1.2)
                  if len(vos) > len(spec["lines"]) else 0)
    return starts, cta_at, end


def mix(spec, vos, starts, cta_at, total, out):
    ins, flt, labs = [], [], []
    at = list(starts) + ([cta_at + 0.15] if len(vos) > len(starts) else [])
    for i, (f, t0) in enumerate(zip(vos, at)):
        ins += ["-i", f]
        ms = int(t0 * 1000)
        flt.append(f"[{i}:a]aresample=44100,adelay={ms}|{ms},apad[v{i}]")
        labs.append(f"[v{i}]")
    k = len(vos)
    bed = spec.get("bed")
    if bed and os.path.exists(_p(bed)):
        ins += ["-stream_loop", "-1", "-i", _p(bed)]
        flt.append(f"[{k}:a]aresample=44100,volume=0.22,afade=t=out:st={total-1.2:.2f}:d=1.2[bed]")
        labs.append("[bed]")
    flt.append(f"{''.join(labs)}amix=inputs={len(labs)}:normalize=0,atrim=0:{total:.2f},"
               f"loudnorm=I=-15:TP=-1.5[a]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(flt), "-map", "[a]",
                    "-ac", "2", "-ar", "44100", out], check=True)


# ---------- end beat ----------

def end_layer(spec, boxes):
    """CTA box + QR + small brand tag, under the stacked captions."""
    import qr
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y = (boxes[-1][2] + boxes[-1][0].height + 70) if boxes else 1100
    if spec.get("cta"):
        cta = box_image(spec["cta"], px=58)
        lay.alpha_composite(cta, ((W - cta.width) // 2, y))
        y += cta.height + 34
    if spec.get("link"):
        card = qr.card(spec["link"], size=300, label=spec.get("qr_label", "SCAN TO SIGN UP"))
        lay.alpha_composite(card, ((W - card.width) // 2, min(y, H - card.height - 120)))
    tag = spec.get("brand", "HSW365 MEDIA")
    f = _font(34)
    d = ImageDraw.Draw(lay)
    tw = d.textlength(tag, font=f)
    d.text(((W - tw) / 2, H - 92), tag, font=f, fill=(255, 255, 255, 200))
    return lay


def build(spec, out):
    work = tempfile.mkdtemp(prefix="irun-caption-")
    vos = voices(spec, work)
    starts, cta_at, total = timeline(spec, vos)
    log(f"{len(spec['lines'])} lines, {total:.1f}s")
    clip, src = broll(spec, work, total)
    log("b-roll from", src)
    boxes = layout(spec["lines"])
    endl = end_layer(spec, boxes)
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(H):  # gentle top/bottom vignette so the boxes and QR read on any shot
        a = int(70 * max(0, (i - H * 0.55) / (H * 0.45)) ** 1.4)
        sd.line([(0, i), (W, i)], fill=(0, 0, 0, a))
    shade = shade.filter(ImageFilter.GaussianBlur(4))
    n = int(total * FPS)
    wav = os.path.join(work, "a.wav")
    mix(spec, vos, starts, cta_at, total, wav)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                          out], stdin=subprocess.PIPE)
    pop_f = 0.18 * FPS
    for i, fr in enumerate(_frames(clip, n)):
        t = i / FPS
        img = fr.convert("RGBA")
        if t >= cta_at - 0.2:
            img.alpha_composite(shade)
        for (bx, x, y), t0 in zip(boxes, starts):
            if t < t0:
                break
            k = (t - t0) * FPS / pop_f
            b = _pop(bx, k)
            img.alpha_composite(b, (x + (bx.width - b.width) // 2, y + (bx.height - b.height) // 2))
        if t >= cta_at:
            a = min(1.0, (t - cta_at) / 0.35)
            el = endl if a >= 1 else Image.fromarray((np.asarray(endl) * [1, 1, 1, a]).astype(np.uint8), "RGBA")
            img.alpha_composite(el)
        p.stdin.write(img.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg encode failed")
    return round(total, 2)


if __name__ == "__main__":
    with open(sys.argv[1]) as fh:
        s = json.load(fh)
    print(json.dumps({"out": sys.argv[2], "seconds": build(s, sys.argv[2])}))
