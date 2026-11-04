"""Build one series episode (engine/series.py) and post it to Instagram through iRun.

  python engine/series_job.py content/series/<slug>.json [--post] [--account hoodstar365]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--account")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    a = ap.parse_args()
    with open(a.spec) as f:
        spec = json.load(f)
    slug = os.path.splitext(os.path.basename(a.spec))[0]
    import series
    os.makedirs(a.out, exist_ok=True)
    video = os.path.join(a.out, f"{slug}-ad.mp4")
    secs = series.build(spec, video, slug=slug)
    print(json.dumps({"video": video, "seconds": secs}))
    if a.post:
        tags = " ".join("#" + t for t in spec.get("hashtags", []))
        subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "--account", a.account or spec.get("account", "hoodstar365"),
                        "--platform", "instagram", "--video", video, "--caption", (spec.get("caption", "") + "\n\n" + tags).strip(),
                        "--mode", os.environ.get("IRUN_MODE", "live")], check=True)


if __name__ == "__main__":
    main()
