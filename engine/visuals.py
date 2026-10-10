"""Scene images for faceless videos: AI-generated from a text prompt in a chosen visual style.

Provider: Pollinations. It works with no key (free tier: lower resolution, and it refuses requests for a
short while after a burst, so iRun waits and retries). Set POLLINATIONS_TOKEN (a key from
enter.pollinations.ai) for sharper models and no shared limit; IRUN_IMAGE_MODEL picks the model. If an image can't be generated after the retries, a soft abstract
backdrop in the style's colours is used so the video still gets made (the run log says so).
"""
import io
import json
import os
import random
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.join(os.path.dirname(__file__), "..")
W, H = 1080, 1920
NO = "no text, no words, no letters, no captions, no watermark, no logo"


def styles():
    with open(os.path.join(ROOT, "config", "styles.json")) as f:
        data = json.load(f)
    return {s["id"]: s for s in data["styles"]}, data.get("default", "cinematic")


def style(style_id):
    all_, default = styles()
    return all_.get(style_id) or all_[default]


def prompt_for(visual, st):
    return f"{visual.strip().rstrip('.')}. {st['prompt']}. Vertical composition. {NO}."


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def backdrop(st, seed, out):
    """Abstract fallback image: two blurred colour fields from the style's tint."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W // 4, H // 4), (10, 10, 15))
    d = ImageDraw.Draw(img)
    for col in st.get("tint", ["#0e4654", "#3e1a5c"]):
        x, y, r = rnd.randint(0, W // 4), rnd.randint(0, H // 4), rnd.randint(150, 230)
        d.ellipse([x - r, y - r, x + r, y + r], fill=_hex(col))
    img = img.filter(ImageFilter.GaussianBlur(60)).resize((W, H), Image.BICUBIC)
    img.save(out, "JPEG", quality=90)
    return out


def _open(r):
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    img.load()
    if min(img.size) < 256:
        raise RuntimeError(f"image too small: {img.size}")
    return img.convert("RGB")


def _pollinations(prompt, seed):
    q = urllib.parse.quote(prompt, safe="")
    token = os.environ.get("POLLINATIONS_TOKEN")
    if token:  # keyed endpoint: sharper models, no shared free-tier limit
        params = {"width": W, "height": H, "seed": seed}
        if os.environ.get("IRUN_IMAGE_MODEL"):
            params["model"] = os.environ["IRUN_IMAGE_MODEL"]
        return _open(requests.get(f"https://gen.pollinations.ai/image/{q}", params=params,
                                  headers={"Authorization": "Bearer " + token}, timeout=180))
    params = {"width": W, "height": H, "seed": seed, "nologo": "true", "private": "true",
              "model": os.environ.get("IRUN_IMAGE_MODEL", "flux")}
    return _open(requests.get(f"https://image.pollinations.ai/prompt/{q}", params=params, timeout=120))


WAITS = [12, 25, 40]  # the free tier allows a short burst, then refuses (HTTP 402/429) until it refills


def scene_image(visual, style_id, seed, out, tries=4):
    """Make one scene image. Returns (path, source) where source is 'pollinations' or 'backdrop'."""
    st = style(style_id)
    prompt = prompt_for(visual, st)
    err = None
    for k in range(tries):
        try:
            _pollinations(prompt, seed + k).save(out, "JPEG", quality=92)
            return out, "pollinations"
        except Exception as e:  # rate limit, timeout, bad image: wait and retry
            err = e
            if k < tries - 1:
                time.sleep(WAITS[min(k, len(WAITS) - 1)])
    print(f"[visuals] image failed after {tries} tries ({err}); using a plain backdrop for this scene")
    return backdrop(st, seed, out), "backdrop"
