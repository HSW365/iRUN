"""Build a scene-based product ad from a spec file with iRun's own engine (AI scene images, voiceover,
word captions, CTA card, scan-to-subscribe QR). No paid video API.

  python engine/make_ad.py content/ads/microroll.json out/microroll-ad.mp4

Spec: {"style": "photoreal", "voice": "en-US-AvaMultilingualNeural", "brand": "HSW365", "name": "...",
       "cta": ["LINE 1", "LINE 2"], "link": "https://...", "scenes": [{"say": "...", "visual": "..."}], ...}
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import faceless  # noqa: E402
import qr  # noqa: E402


def main(spec_path, out_path):
    with open(spec_path) as f:
        spec = json.load(f)
    if spec.get("kind") == "trailer":  # trailer-cut micro-drama (engine/trailer.py)
        import trailer
        print(json.dumps({"out": out_path, "seconds": trailer.build(spec, out_path)}))
        return
    if spec.get("kind") == "caption":  # lo-fi POV caption-box ad (engine/caption_ad.py)
        import caption_ad
        print(json.dumps({"out": out_path, "seconds": caption_ad.build(spec, out_path)}))
        return
    os.environ.setdefault("IRUN_IMAGE_TRIES", "8")
    if spec.get("voice"):
        os.environ["IRUN_EDGE_VOICE"] = spec["voice"]
    script = faceless.clean(spec)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    work = tempfile.mkdtemp(prefix="irun-ad-")
    res = faceless.build(script, spec.get("style", "photoreal"), work, out_path, tuple(spec["cta"]),
                         spec.get("brand", "HSW365"), spec.get("name", script["title"]), seed=spec.get("seed"))
    qr.stamp(out_path, spec.get("link"), x="(W-w)/2", y="H-h-70")  # under the CTA card, centered
    print(json.dumps({"out": out_path, "voice": res["voice"], "seconds": res.get("seconds"),
                      "images": [m.get("source") for m in res.get("media", [])]}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
