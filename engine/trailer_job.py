"""iRun trailer job: one spec in, a finished trailer ad out (and posted).

  python engine/trailer_job.py content/ads/<slug>-trailer.json [--post] [--account hoodstar365] [--out out]

The spec is a normal engine/trailer.py spec plus two optional build keys:
  "shot_prompts": {"<shot name>": "<cinematic still prompt>"}   any shot missing from shots_dir is generated (Pollinations)
  "shot_refs":    {"<shot name>": "<public image url>"}        product photo the shot must carry (image-to-image)
  "composites":   {"<shot>": {"bg": "<shot>", "fg": "<cutout.png>", "h": 0.8}}  a real person cut out and lit into a shot
  "voice":        "owner"                                       VO in Elvin's own cloned voice (engine/myvoice.py)
  "look":         "bright"                                      daylight/high-key grade instead of the dark one
  "vo_lines":     [[at_seconds, "narrator line"], ...]            recorded with engine/narrator.py (ElevenLabs when
                                                                 IRUN_NARRATOR=elevenlabs, else free Kokoro) and wired in
                                                                 as spec["vo"] with burned-in captions
Shots and voice files are cached, so re-running only re-renders. IRUN_FRESH_SHOTS=1 / IRUN_FRESH_VO=1 rebuild them.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
LOOK = ("cinematic film still, anamorphic, high-contrast grade, shallow depth of field, film grain, photoreal, 35mm, "
        "vertical composition, no text, no logos, no watermark")
BRIGHT = ("cinematic film still, bright high-key daylight, vivid saturated color, sunlit, clean airy exposure, "
          "shallow depth of field, photoreal, 35mm, vertical composition, no text, no logos, no watermark")


def shots(spec, seed):
    import visuals
    d = os.path.join(ROOT, spec["shots_dir"])
    os.makedirs(d, exist_ok=True)
    look = BRIGHT if spec.get("look") == "bright" else LOOK
    refs = spec.get("shot_refs", {})
    for i, (name, prompt) in enumerate(spec.get("shot_prompts", {}).items()):
        out = os.path.join(d, f"{name}.jpg")
        if os.path.exists(out) and not os.environ.get("IRUN_FRESH_SHOTS"):
            print(f"[shots] {name}: cached"); continue
        _, src = visuals.scene_image(f"{prompt}, {look}", "photoreal", seed + i * 7, out, ref=refs.get(name))
        if src.startswith("pollinations"):
            clean(out)
        print(f"[shots] {name}: {src}")
    for name, c in spec.get("composites", {}).items():
        composite(d, name, c)


def clean(path, cut=0.055):
    """Free-tier images carry a small watermark along the bottom edge: crop it off and refit to 9:16."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.crop((int(w * cut / 2), 0, int(w * (1 - cut / 2)), int(h * (1 - cut))))
    im.resize((1080, 1920), Image.LANCZOS).save(path, "JPEG", quality=93)


def composite(d, name, c):
    """Put a cut-out person (PNG with alpha) into a generated backplate, lit to match it:
    {"bg": "<shot>", "fg": "assets/.../cutout.png", "h": 0.8, "x": 0.5, "bottom": 1.0, "rim": ["#22d3ee", "#ec4899"]}"""
    import numpy as np
    import visuals
    from PIL import Image, ImageFilter
    bg = Image.open(os.path.join(d, f"{c['bg']}.jpg")).convert("RGB").resize((1080, 1920), Image.LANCZOS)
    fg = Image.open(os.path.join(ROOT, c["fg"])).convert("RGBA")
    if c.get("crop"):  # [x0, y0, x1, y1] fractions of the cut-out, e.g. a close-up of the head
        w, h = fg.size; x0, y0, x1, y1 = c["crop"]
        fg = fg.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    th = int(1920 * c.get("h", 0.8)); fg = fg.resize((int(fg.width * th / fg.height), th), Image.LANCZOS)
    a = np.asarray(fg).astype(np.float32); rgb, al = a[..., :3], a[..., 3:4] / 255
    b = np.asarray(bg).astype(np.float32)
    tone = b.reshape(-1, 3).mean(0)  # pull the person toward the scene's colour and exposure
    rgb = rgb * 0.78 + tone * 0.22 * (rgb.mean() / max(1, tone.mean()))
    rgb = rgb * c.get("expose", 0.82)
    edge = np.asarray(Image.fromarray((al[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(7))).astype(np.float32)[..., None] / 255
    rim = np.clip((al - edge) * 2.2, 0, 1) * al  # thin band inside the silhouette edge
    xs = np.linspace(0, 1, rgb.shape[1], dtype=np.float32)[None, :, None]
    cols = [np.array(visuals._hex(x), np.float32) for x in c.get("rim", ["#22d3ee", "#ec4899"])]
    rgb = rgb + rim * (cols[0] * (1 - xs) + cols[-1] * xs) * 0.45
    px = int(1080 * c.get("x", 0.5) - fg.width / 2); py = int(1920 * c.get("bottom", 1.0) - fg.height)
    sh = Image.new("L", (1080, 1920), 0)  # contact shadow under the feet
    sh.paste(Image.new("L", (int(fg.width * 0.9), 60), 170), (px + int(fg.width * 0.05), py + fg.height - 40))
    sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(30))).astype(np.float32)[..., None] / 255
    b = b * (1 - sh * 0.7)
    x0, y0 = max(0, px), max(0, py); x1, y1 = min(1080, px + fg.width), min(1920, py + fg.height)
    sub = slice(y0 - py, y1 - py), slice(x0 - px, x1 - px)
    b[y0:y1, x0:x1] = b[y0:y1, x0:x1] * (1 - al[sub]) + rgb[sub] * al[sub]
    Image.fromarray(np.clip(b, 0, 255).astype(np.uint8)).save(os.path.join(d, f"{name}.jpg"), "JPEG", quality=93)
    m = np.zeros((1920, 1080), np.float32); m[y0:y1, x0:x1] = al[sub][..., 0]
    Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(d, f"{name}.mask.png"))  # keeps FX behind the person
    print(f"[shots] {name}: composite of {c['fg']} on {c['bg']}")


def voice(spec, slug):
    lines = spec.get("vo_lines") or []
    if not lines:
        return
    d = os.path.join(ROOT, "assets", "voice", slug)
    files = [os.path.join(d, f"vo{i}.wav") for i in range(1, len(lines) + 1)]
    if os.environ.get("IRUN_FRESH_VO") or not all(os.path.exists(f) for f in files):
        who = "myvoice.py" if spec.get("voice") == "owner" else "narrator.py"  # owner = Elvin's own cloned voice
        subprocess.run([sys.executable, os.path.join(HERE, who), d, *[t for _, t in lines]], check=True)
    spec["vo"] = [{"file": f"assets/voice/{slug}/vo{i}.wav", "at": at, "text": t}
                  for i, (at, t) in enumerate(lines, 1)]
    spec.setdefault("vo_captions", True)


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
    slug = os.path.basename(a.spec).replace(".json", "").replace("-trailer", "")
    shots(spec, a.seed)
    voice(spec, slug)
    import trailer
    os.makedirs(a.out, exist_ok=True)
    video = os.path.join(a.out, f"{slug}-ad.mp4")
    secs = trailer.build(spec, video)
    print(json.dumps({"video": video, "seconds": secs}))
    if a.post:
        tags = " ".join("#" + t for t in spec.get("hashtags", []))
        subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "--account", a.account or spec.get("account", "hoodstar365"),
                        "--platform", "instagram", "--video", video, "--caption", (spec.get("caption", "") + "\n\n" + tags).strip(),
                        "--mode", os.environ.get("IRUN_MODE", "live")], check=True)


if __name__ == "__main__":
    main()
