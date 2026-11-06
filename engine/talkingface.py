"""iRun Talking Face: a face that speaks your script, lip-synced, as a branded 9:16 ad (free, open-source, CPU).

  python engine/talkingface.py content/faces/<slug>.json [--post] [--account hoodstar365] [--out out]

Spec:
  {
    "face": "ai",                                  "ai" = an original AI-generated person (never a real person), or a
                                                   path under assets/faces/ to a photo of YOU or someone who said yes
    "face_prompt": "confident man in his 30s, black hoodie, studio light",   used when face is "ai"
    "script": ["Stop scrolling.", "iRun builds your ads and posts them while you sleep."],
    "voice": "narrator",                           "narrator" (free Kokoro, original voice) or "owner" (your cloned voice)
    "qr": "https://...signup",                     scan-to-subscribe link shown at the end
    "brand": "iRUN BY HSW365", "accent": "#22d3ee",
    "caption": "...", "hashtags": ["irun", "aiads"], "account": "hoodstar365"
  }

Engine: SadTalker (Apache-2.0) does the lip-sync + natural head motion from one photo. IRUN_FACE_ENHANCE=1 adds a
GFPGAN face clean-up pass (sharper, but ~3x slower on a free CPU runner).
Set SADTALKER_DIR to its checkout (the workflow installs it). Real people's faces, celebrities included, are refused
unless the photo is in assets/faces/ (yours, or a person who gave permission).
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
FACES = os.path.join(ROOT, "assets", "faces")
FONTS = os.path.join(ROOT, "assets", "fonts")
W, H = 1080, 1920
AI_LOOK = ("photorealistic portrait photo of an original fictional person, not a celebrity, head and shoulders, "
           "facing the camera, looking into the lens, mouth closed, neutral expression, sharp focus on the face, "
           "soft studio key light, dark moody background, 85mm, high detail skin, no text, no watermark")


def sh(*cmd):
    subprocess.run(list(cmd), check=True)


def make_face(spec, work, seed):
    """Return the path of the face photo to animate."""
    face = spec.get("face", "ai")
    out = os.path.join(work, "face.jpg")
    if face == "ai":
        import visuals
        from PIL import Image
        prompt = f"{spec.get('face_prompt', 'confident person in their 30s')}, {AI_LOOK}"
        _, src = visuals.scene_image(prompt, "photoreal", seed, out)
        if not src.startswith("pollinations"):
            raise SystemExit("[face] the AI face could not be generated; try again")
        im = Image.open(out).convert("RGB")
        w, h = im.size  # trim the free-tier watermark strip along the bottom
        im.crop((0, 0, w, int(h * 0.94))).save(out, "JPEG", quality=95)
        print(f"[face] AI face generated ({src})")
        return square(out)
    path = os.path.abspath(os.path.join(ROOT, face))
    if not path.startswith(FACES + os.sep) or not os.path.exists(path):
        raise SystemExit("[face] use \"ai\" or a photo in assets/faces/ (you, or someone who gave permission)")
    shutil.copy(path, out)
    return square(out)


def square(path):
    """Square crop that keeps the head (upper part of a portrait), 768px, so the framed face never stretches."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if h > w:
        top = int((h - w) * 0.25)
        im = im.crop((0, top, w, top + w))
    elif w > h:
        left = (w - h) // 2
        im = im.crop((left, 0, left + h, h))
    im.resize((768, 768), Image.LANCZOS).save(path, "JPEG", quality=95)
    return path


def make_voice(spec, work):
    lines = spec["script"] if isinstance(spec["script"], list) else [spec["script"]]
    d = os.path.join(work, "vo")
    who = "myvoice.py" if spec.get("voice") == "owner" else "narrator.py"
    sh(sys.executable, os.path.join(HERE, who), d, *lines)
    files = [os.path.join(d, f"vo{i}.wav") for i in range(1, len(lines) + 1)]
    gap = os.path.join(work, "gap.wav")
    sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.35", gap)
    lst = os.path.join(work, "vo.txt")
    with open(lst, "w") as f:
        for i, p in enumerate(files):
            f.write(f"file '{p}'\n")
            if i < len(files) - 1:
                f.write(f"file '{gap}'\n")
    out = os.path.join(work, "voice.wav")
    sh("ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ac", "1", "-ar", "16000", out)
    hq = os.path.join(work, "voice-hq.wav")
    sh("ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ac", "2", "-ar", "44100", hq)
    return out, hq, lines


def lipsync(face, audio, work):
    st = os.environ.get("SADTALKER_DIR", os.path.join(ROOT, ".sadtalker"))
    res = os.path.join(work, "st")
    cmd = [os.environ.get("SADTALKER_PY", sys.executable), "inference.py", "--driven_audio", audio,
           "--source_image", face, "--result_dir", res, "--preprocess", "full", "--still", "--size", "256",
           "--expression_scale", "1.1"]
    if os.environ.get("IRUN_FACE_ENHANCE", "0") == "1":
        cmd += ["--enhancer", "gfpgan"]
    if os.environ.get("IRUN_GPU") != "1":
        cmd.append("--cpu")
    subprocess.run(cmd, cwd=st, check=True)
    vids = sorted(glob.glob(os.path.join(res, "*.mp4")), key=os.path.getmtime)
    if not vids:
        raise SystemExit("[lipsync] no video came out")
    return vids[-1]


def _font(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def overlay(spec, work):
    """Transparent 1080x1920 layer: brand top-left, accent rule, frame glow."""
    from PIL import Image, ImageDraw, ImageFilter
    from visuals import _hex
    acc = tuple(_hex(spec.get("accent", "#22d3ee")))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    brand = spec.get("brand", "iRUN BY HSW365")
    d.text((70, 90), brand, font=_font("BarlowCondensed-ExtraBold.ttf", 64), fill=(242, 242, 247, 255))
    d.rectangle((70, 172, 250, 180), fill=acc + (255,))
    tag = spec.get("tag", "TURN NEGATIVE INTO POSITIVE")
    d.text((70, 196), tag, font=_font("SpaceMono-Bold.ttf", 26), fill=(160, 160, 180, 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.rounded_rectangle((60, 330, W - 60, 330 + W - 120), radius=44, outline=acc + (200,), width=10)
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    im = Image.alpha_composite(glow, im)
    ImageDraw.Draw(im).rounded_rectangle((60, 330, W - 60, 330 + W - 120), radius=44, outline=acc + (255,), width=3)
    p = os.path.join(work, "overlay.png")
    im.save(p)
    return p


def caption_cards(lines, work, total):
    """One PNG per script line, timed by word count, shown under the face."""
    from PIL import Image, ImageDraw
    words = [max(1, len(l.split())) for l in lines]
    per = total / sum(words)
    cards, t = [], 0.0
    f = _font("BarlowCondensed-ExtraBold.ttf", 78)
    for i, (line, n) in enumerate(zip(lines, words)):
        im = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rows, cur = [], ""
        for w in line.upper().split():
            test = (cur + " " + w).strip()
            if d.textlength(test, font=f) > W - 160 and cur:
                rows.append(cur); cur = w
            else:
                cur = test
        rows.append(cur)
        y = 10
        for r in rows[:4]:
            x = (W - d.textlength(r, font=f)) / 2
            d.text((x, y), r, font=f, fill=(242, 242, 247, 255), stroke_width=4, stroke_fill=(10, 10, 15, 255))
            y += 92
        p = os.path.join(work, f"cap{i}.png")
        im.save(p)
        cards.append((p, t, t + n * per))
        t += n * per
    return cards


def compose(spec, head, hq, lines, work, out):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", hq],
                               capture_output=True, text=True, check=True).stdout.strip())
    ov = overlay(spec, work)
    import qr
    end = dur - qr.SECONDS + 0.4 if spec.get("qr") else dur + 0.4  # captions clear out before the QR card lands
    caps = [(p, s, min(e, end)) for p, s, e in caption_cards(lines, work, dur) if s < end]
    box = W - 120
    from PIL import Image, ImageDraw
    mask = Image.new("L", (box, box), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, box - 1, box - 1), radius=44, fill=255)
    mp = os.path.join(work, "mask.png")
    mask.save(mp)
    inputs = ["-i", head, "-i", hq, "-loop", "1", "-i", ov, "-loop", "1", "-i", mp]
    for p, _, _ in caps:
        inputs += ["-loop", "1", "-i", p]
    f = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:2,eq=brightness=-0.32:saturation=0.7[bg];"
         f"[0:v]scale={box}:{box}:flags=lanczos,format=rgba[sq];[3:v]format=gray[m];[sq][m]alphamerge[fg];"
         f"[bg][fg]overlay=60:330[a];[a][2:v]overlay=0:0[b]")
    last = "b"
    for i, (_, s, e) in enumerate(caps):
        f += f";[{last}][{i + 4}:v]overlay=0:{330 + box + 70}:enable='between(t,{s:.2f},{e:.2f})'[c{i}]"
        last = f"c{i}"
    f += f";[{last}]fps=30,format=yuv420p[v]"
    sh("ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f, "-map", "[v]", "-map", "1:a", "-t", f"{dur + 0.4:.2f}",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)
    return dur


def build(spec, out, seed=3650):
    work = tempfile.mkdtemp(prefix="irun-face-")
    face = make_face(spec, work, seed)
    audio, hq, lines = make_voice(spec, work)
    head = lipsync(face, audio, work)
    secs = compose(spec, head, hq, lines, work, out)
    if spec.get("qr"):
        import qr
        qr.stamp(out, spec["qr"], x="(W-w)/2", y="H-h-150")
    shutil.copy(face, re.sub(r"\.mp4$", "-face.jpg", out))
    return secs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--account")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--seed", type=int, default=3650)
    a = ap.parse_args()
    with open(a.spec) as f:
        spec = json.load(f)
    slug = os.path.basename(a.spec).replace(".json", "")
    os.makedirs(a.out, exist_ok=True)
    video = os.path.join(a.out, f"{slug}-face.mp4")
    secs = build(spec, video, a.seed)
    print(json.dumps({"video": video, "seconds": round(secs, 1)}))
    if a.post:
        tags = " ".join("#" + t for t in spec.get("hashtags", []))
        sh(sys.executable, os.path.join(HERE, "run.py"), "--account", a.account or spec.get("account", "hoodstar365"),
           "--platform", "instagram", "--video", video, "--caption", (spec.get("caption", "") + "\n\n" + tags).strip(),
           "--mode", os.environ.get("IRUN_MODE", "live"))


if __name__ == "__main__":
    main()
