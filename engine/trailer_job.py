"""iRun trailer job: one spec in, a finished trailer ad out (and posted).

  python engine/trailer_job.py content/ads/<slug>-trailer.json [--post] [--account hoodstar365] [--out out]

The spec is a normal engine/trailer.py spec plus two optional build keys:
  "shot_prompts": {"<shot name>": "<cinematic still prompt>"}   any shot missing from shots_dir is generated (Pollinations)
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


def shots(spec, seed):
    import visuals
    d = os.path.join(ROOT, spec["shots_dir"])
    os.makedirs(d, exist_ok=True)
    for i, (name, prompt) in enumerate(spec.get("shot_prompts", {}).items()):
        out = os.path.join(d, f"{name}.jpg")
        if os.path.exists(out) and not os.environ.get("IRUN_FRESH_SHOTS"):
            print(f"[shots] {name}: cached"); continue
        _, src = visuals.scene_image(f"{prompt}, {LOOK}", "photoreal", seed + i * 7, out)
        print(f"[shots] {name}: {src}")


def voice(spec, slug):
    lines = spec.get("vo_lines") or []
    if not lines:
        return
    d = os.path.join(ROOT, "assets", "voice", slug)
    files = [os.path.join(d, f"vo{i}.wav") for i in range(1, len(lines) + 1)]
    if os.environ.get("IRUN_FRESH_VO") or not all(os.path.exists(f) for f in files):
        subprocess.run([sys.executable, os.path.join(HERE, "narrator.py"), d, *[t for _, t in lines]], check=True)
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
