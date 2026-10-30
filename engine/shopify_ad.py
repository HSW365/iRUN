"""iRun Shopify ads: point iRun at any product on a Shopify store and it builds the house trailer ad for it and posts it.

  python engine/shopify_ad.py hsw365-glow-led-red-light-therapy-mask                     build spec + shots + VO + video
  python engine/shopify_ad.py https://hsw365.co/products/<handle> --post                  ...and post to @hoodstar365 IG
  python engine/shopify_ad.py <handle> --store client-store.com --account <client id> --post

What it does (free route, no paid API):
  1. Reads the product from the store's public storefront feed (/products/<handle>.js): title, price, variants, photos.
  2. Picks a micro-drama playbook from the product type/tags (beauty, wellness, apparel, tech, default) and writes a
     ~19s trailer spec in the house format (engine/trailer.py): cold open, title slam, reaction cuts, a spec card built
     from the product, 3 neon slam words, callback, payoff, end card.
  3. Makes the cinematic stills (Pollinations, free) plus a hero shot from the store's own product photo.
  4. Records the narrator (engine/narrator.py: ElevenLabs when IRUN_NARRATOR=elevenlabs, else free Kokoro).
  5. Renders the trailer. The end-card QR goes straight to checkout for that product (cart permalink), not the homepage.
  6. --post: posts it to Instagram through iRun (engine/run.py --video).
The spec is saved to content/ads/<slug>-trailer.json so it can be re-cut by hand and re-rendered.
"""
import argparse
import html
import io
import json
import os
import re
import subprocess
import sys

import requests
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
W, H = 1080, 1920

# ---------- playbooks: one micro-drama per kind of product ----------
# {title} {short} {price} are filled from the product. Shot prompts are cinematic stills, vertical, no text.
LOOK = ("cinematic film still, anamorphic, high-contrast grade, shallow depth of field, film grain, photoreal, 35mm, "
        "vertical composition, tasteful, fully clothed, no text, no logos, no watermark")
PLAYBOOKS = {
    "beauty": {
        "match": ["beauty", "skin", "mask", "led", "facial", "glow", "serum", "red light"],
        "accent": "#ff2d55",
        "presents": "HSW365 PRESENTS",
        "open_impact": "TIRED", "callback_impact": "GLOWING",
        "slams": ["YOUR", "GLOW", "BACK"],
        "char": ("the same woman throughout: a 32-year-old Black woman with deep brown skin, shoulder-length natural "
                 "curly black hair, small gold hoop earrings"),
        "shots": {
            "mirror": "{char}, wearing an oversized cream knit sweater, leaning toward a bathroom mirror at dawn, cold "
                      "blue light, tired eyes, fingertips on her cheek, quiet frustration, dark moody grade",
            "shelf": "a crowded marble bathroom counter of half-used skincare bottles and jars, cold blue light, one "
                     "bottle tipped over, dark moody grade",
            "closeup": "{char}, extreme close-up of her eyes and cheek in a mirror reflection, cold blue light, skin "
                       "texture visible, weary, dark moody grade",
            "night": "{char}, wearing an oversized cream knit sweater, sitting on the edge of her bed at night, city "
                     "lights through the window, lifting the lid of a matte black gift box with deep red light glowing "
                     "out of it onto her face, curious, dark moody grade",
            "glow": "{char}, wearing an oversized cream knit sweater, relaxing in a dark room, her face covered by a "
                    "black LED light therapy beauty mask glowing bright red, red light falling on her sweater, serene",
            "morning": "{char}, wearing a white linen shirt, at a bathroom mirror flooded with bright golden morning "
                       "sunlight, radiant healthy skin, small confident smile, warm tones",
            "out": "{char}, wearing a camel coat, walking out of a modern apartment building onto a city street at "
                   "golden hour, confident, warm sunlight, people glancing at her",
        },
        "open": "mirror", "scenes": ["shelf", "closeup", "night"], "slam_shots": ["glow", "product", "glow"],
        "callback": "morning", "payoff": ["out", "product"],
        "subs": ["", "", "", ""],
        "tagline": "The spa, at home. Ten minutes a day.",
        "vo": [[0.3, "Every morning, the mirror told her the same story."],
               [4.0, "Ten products. Nothing changed."],
               [8.0, "Then she gave it ten minutes of red light."],
               [12.4, "Now the mirror tells a new one."],
               [15.6, "{short}. Scan to get yours."]],
        "fine": "For cosmetic use. Results vary.",
    },
    "wellness": {
        "match": ["massager", "massage", "wellness", "recovery", "posture", "pain", "relax", "neck"],
        "accent": "#22d3ee",
        "presents": "HSW365 PRESENTS",
        "open_impact": "LOCKED", "callback_impact": "RELEASED",
        "slams": ["LET", "IT", "GO"],
        "shots": {
            "desk": "a man in his 30s at a desk at 2am, lit only by a laptop, rubbing a stiff neck, exhausted",
            "wince": "close-up of a man wincing, hand gripping the back of his neck, cold blue light",
            "car": "a woman in a parked car at night, head back against the seat, eyes closed, tension in her shoulders",
            "night": "the same man on a dark couch holding a sleek neck massager, cyan light",
            "relief": "a man with a neck massager on, eyes closed, deep relief, cyan rim light, dark room",
            "morning": "the same man stretching by a window in warm morning light, loose and rested, smiling",
            "out": "the same man walking out the door in golden hour light, confident, light on his feet",
        },
        "open": "desk", "scenes": ["wince", "car", "night"], "slam_shots": ["relief", "relief", "relief"],
        "callback": "morning", "payoff": ["out", "product"],
        "subs": ["", "Carrying it all day.", "", ""],
        "tagline": "Ten minutes. Shoulders down.",
        "vo": [[0.3, "You carry it all day."], [4.0, "In the car. At the desk. In your sleep."],
               [8.0, "Ten minutes. That's all it takes."], [12.4, "Wake up loose."], [15.6, "{short}. Scan to get yours."]],
        "fine": "Not a medical device. Results vary.",
    },
    "apparel": {
        "match": ["tee", "shirt", "hoodie", "apparel", "streetwear", "clothing", "hat", "collection"],
        "accent": "#f59e0b",
        "presents": "HOODSTARWORLD PRESENTS",
        "open_impact": "NOBODY", "callback_impact": "SOMEBODY",
        "slams": ["WEAR", "YOUR", "STORY"],
        "shots": {
            "street": "a young man alone on a wet city street at night under a flickering streetlight, hood up, determined",
            "stare": "close-up of a man's face, rain on his skin, staring down the camera, sodium light",
            "crowd": "a crowd walking past a man who stands still on a busy sidewalk at night, motion blur",
            "night": "the same man in a dim room laying out a bold graphic streetwear tee on a bed",
            "stage": "the same man stepping into a spotlight wearing a bold graphic streetwear tee, smoke, amber light",
            "morning": "the same man on a rooftop at sunrise wearing the tee, arms open, golden light",
            "out": "the same man walking through a crowd that turns to look at him, golden hour, confident",
        },
        "open": "street", "scenes": ["stare", "crowd", "night"], "slam_shots": ["stage", "stage", "stage"],
        "callback": "morning", "payoff": ["out", "product"],
        "subs": ["", "They walked right past.", "", ""],
        "tagline": "Turn negative into positive.",
        "vo": [[0.3, "They looked right through him."], [4.0, "So he stopped waiting to be seen."],
               [8.0, "And put his story on his chest."], [12.4, "Now they look twice."], [15.6, "{short}. Scan to cop it."]],
        "fine": "",
    },
    "default": {
        "match": [],
        "accent": "#a855f7",
        "presents": "HSW365 PRESENTS",
        "open_impact": "STUCK", "callback_impact": "UPGRADED",
        "slams": ["LEVEL", "IT", "UP"],
        "shots": {
            "dark": "a person alone in a dark room lit by a phone screen, frustrated, late night",
            "sigh": "close-up of a frustrated face, cold blue light, exhale",
            "clock": "a wall clock at 3am in a dark kitchen, cold light",
            "night": "the same person opening a sleek premium package on a table, purple rim light",
            "power": "the same person using a sleek premium gadget, purple glow lighting the room, focused",
            "morning": "the same person in warm morning light, relaxed, smiling",
            "out": "the same person walking out into golden hour light, confident",
        },
        "open": "dark", "scenes": ["sigh", "clock", "night"], "slam_shots": ["power", "power", "power"],
        "callback": "morning", "payoff": ["out", "product"],
        "subs": ["", "Another night. Same problem.", "", ""],
        "tagline": "Upgrade the everyday.",
        "vo": [[0.3, "Same night. Same problem."], [4.0, "You've tried everything."], [8.0, "Not this."],
               [12.4, "Everything changes."], [15.6, "{short}. Scan to get yours."]],
        "fine": "",
    },
}


def pick_playbook(p):
    hay = " ".join([p.get("type", ""), p.get("title", ""), " ".join(p.get("tags", []))]).lower()
    best, score = "default", 0
    for k, pb in PLAYBOOKS.items():
        n = sum(1 for m in pb["match"] if m in hay)
        if n > score:
            best, score = k, n
    return best


# ---------- product ----------
def parse(ref, store):
    m = re.search(r"https?://([^/]+)/products/([^/?#]+)", ref)
    return (m.group(1), m.group(2)) if m else (store, ref.strip("/"))


def fetch(store, handle):
    r = requests.get(f"https://{store}/products/{handle}.js", timeout=30, headers={"User-Agent": "iRun/1.0"})
    r.raise_for_status()
    d = r.json()
    v = next((x for x in d["variants"] if x.get("available")), d["variants"][0])
    imgs = ["https:" + u if u.startswith("//") else u for u in d.get("images", [])]
    text = html.unescape(re.sub(r"<[^>]+>", "\n", d.get("description", "")))
    bullets = [ln.strip() for ln in text.split("\n") if 6 < len(ln.strip()) < 70][:12]
    tags = d.get("tags", [])
    return {"store": store, "handle": handle, "title": d["title"], "type": d.get("type", ""),
            "tags": tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(",")],
            "vendor": d.get("vendor", ""), "price": v["price"] / 100, "variant": v["id"], "images": imgs,
            "bullets": bullets, "url": f"https://{store}/products/{handle}",
            "checkout": f"https://{store}/cart/{v['id']}:1"}


def short_name(title):
    """'HSW365 GLOW — LED Red Light Therapy Mask' -> 'HSW365 GLOW'"""
    s = re.split(r"\s[—–\-|:]\s", title)[0].strip()
    return s if len(s) <= 22 else " ".join(s.split()[:3])


def spoken(s):
    return re.sub(r"HSW365", "H S W three sixty five", s, flags=re.I)


def _trim(s, n):
    out = ""
    for w in s.split():
        if len(out) + len(w) + 1 > n:
            break
        out = (out + " " + w).strip()
    return out or s[:n]


def card_rows(p):
    keep = [b for b in p["bullets"] if not re.match(r"(?i)(start|place|press|relax|follow|for cosmetic|do not)", b)]
    rows = []
    for b in keep[:3]:
        m = re.split(r"\s(?:with|that|for|,)\s|,\s", b, maxsplit=1)
        label, rest = (m[0], m[1]) if len(m) > 1 else (" ".join(b.split()[:3]), " ".join(b.split()[3:]) or "included")
        rows.append([_trim(label, 24), _trim(rest, 28)])
    return rows or [["Price", f"${p['price']:,.0f}"], ["Ships", "from hsw365.co"], ["Checkout", "scan the QR"]]


# ---------- shots ----------
def hero_shot(url, accent, out):
    """Store photo -> 1080x1920 hero: blurred dark fill, product centred with an accent glow."""
    im = Image.open(io.BytesIO(requests.get(url, timeout=60).content)).convert("RGB")
    s = max(W / im.width, H / im.height)
    bg = im.resize((int(im.width * s) + 1, int(im.height * s) + 1)).crop((0, 0, W, H))
    bg = bg.filter(ImageFilter.GaussianBlur(40)).point(lambda x: int(x * 0.28))
    glow = Image.new("RGB", (W, H), (0, 0, 0)); g = ImageDraw.Draw(glow)
    c = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    g.ellipse((W * 0.1, H * 0.25, W * 0.9, H * 0.7), fill=c)
    bg = Image.blend(bg, glow.filter(ImageFilter.GaussianBlur(160)), 0.35)
    k = min(W * 0.88 / im.width, H * 0.55 / im.height)
    fg = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, int(H * 0.47 - fg.height / 2)))
    bg.save(out, "JPEG", quality=93)


def make_shots(pb, p, shots_dir, seed):
    import visuals
    os.makedirs(shots_dir, exist_ok=True)
    src = {}
    char = pb.get("char", "")
    for i, (name, prompt) in enumerate(pb["shots"].items()):
        out = os.path.join(shots_dir, f"{name}.jpg")
        if os.path.exists(out) and not os.environ.get("IRUN_FRESH_SHOTS"):
            src[name] = "cached"; continue
        # character shots share one seed so the same person carries through the whole trailer
        s = seed if "{char}" in prompt else seed + 101 + i * 7
        _, src[name] = visuals.scene_image(f"{prompt.format(char=char)}, {LOOK}", "photoreal", s, out)
    if p["images"]:
        hero_shot(p["images"][0], pb["accent"], os.path.join(shots_dir, "product.jpg"))
        src["product"] = "store photo"
        import shutil  # a shot that failed to generate never airs as a plain backdrop: the real product stands in
        for name, how in src.items():
            if how == "backdrop":
                shutil.copy(os.path.join(shots_dir, "product.jpg"), os.path.join(shots_dir, f"{name}.jpg"))
                src[name] = "store photo (fallback)"
    else:
        pb["payoff"] = [x for x in pb["payoff"] if x != "product"] or ["morning"]
    return src


# ---------- spec ----------
def overrides(handle):
    """config/shopify_ads.json: {"<handle>": {"playbook", "accent", "tagline", "rows", "vo": [[at, line]], "short"}}"""
    try:
        with open(os.path.join(ROOT, "config", "shopify_ads.json")) as f:
            return json.load(f).get(handle, {})
    except FileNotFoundError:
        return {}


def build_spec(p, kind, slug, account):
    ov = overrides(p["handle"])
    pb = dict(PLAYBOOKS[kind], **{k: v for k, v in ov.items() if k in ("accent", "tagline", "vo", "fine", "slams")})
    short = ov.get("short") or short_name(p["title"])
    sc = pb["scenes"]
    scenes = [{"shot": sc[0], "sub": pb["subs"][0], "cy": 0.45, "zoom": [1.04, 1.16]},
              {"shot": sc[1], "sub": pb["subs"][1], "cy": 0.42, "zoom": [1.12, 1.26]},
              {"card": {"title": f"{short} · what's inside", "tag": "INCLUDED", "rows": ov.get("rows") or card_rows(p)},
               "bg": sc[2]},
              {"shot": sc[2], "sub": pb["subs"][3], "cy": 0.4, "zoom": [1.06, 1.18], "tense": True}]
    for s in scenes:  # the narrator's lines are burned in as captions, so scenes carry no extra subtitles
        s.pop("sub", None)
    slams = [{"word": w, "shot": pb["slam_shots"][i], "cy": 0.42, "zoom": [1.0 + 0.06 * i, 1.12 + 0.06 * i]}
             for i, w in enumerate(pb["slams"])]
    payoff = [{"shot": x, "cy": 0.45, "warm": True} for x in pb["payoff"]]
    words = short.split()
    wordmark = [words[0] + " ", " ".join(words[1:])] if len(words) > 1 else [short, ""]
    spec = {
        "kind": "trailer", "account": account, "product": p["handle"], "platform": "instagram",
        "shots_dir": f"content/shots/{slug}", "accent": pb["accent"], "title": short.upper(),
        "presents": pb["presents"], "end_dur": 4.2,
        "open": {"shot": pb["open"], "impact": pb["open_impact"], "cy": 0.42, "zoom": [1.0, 1.1], "dur": 2.0},
        "scenes": scenes, "slams": slams,
        "callback": {"shot": pb["callback"], "impact": pb["callback_impact"], "warm": True},
        "payoff": payoff,
        "end": {"wordmark": wordmark, "tagline": pb["tagline"], "cta": "SCAN TO SHOP",
                "lines": [f"${p['price']:,.0f}  ·  STRAIGHT TO CHECKOUT", p["store"].upper()],
                "fine": pb["fine"], "link": p["checkout"]},
        "caption": "",
        "hashtags": [],
    }
    lines = [(at, t.format(short=short, title=p["title"], price=f"{p['price']:,.0f}")) for at, t in pb["vo"]]
    spec["vo"] = [{"file": f"assets/voice/{slug}/vo{i}.wav", "at": at, "text": t} for i, (at, t) in enumerate(lines, 1)]
    spec["vo_captions"] = True; spec["duck"] = 0.55
    tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in p["tags"]][:6]
    spec["hashtags"] = [t for t in tags if t] + ["hsw365", "hsw365co", "shopnow"]
    spec["caption"] = (f"{lines[0][1]} {lines[2][1]} {p['title']}, ${p['price']:,.0f}. Scan the QR in the video to go "
                       f"straight to checkout, or shop {p['url'].replace('https://', '')} (link in bio).")
    return spec, [spoken(t) for _, t in lines]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("product", help="product handle or full product URL")
    ap.add_argument("--store", default="hsw365.co")
    ap.add_argument("--account", default="hoodstar365")
    ap.add_argument("--playbook", choices=list(PLAYBOOKS), help="force a playbook (default: picked from the product)")
    ap.add_argument("--seed", type=int, default=3650)
    ap.add_argument("--spec-only", action="store_true", help="write the spec and stop")
    ap.add_argument("--post", action="store_true", help="post the finished ad to Instagram through iRun")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    a = ap.parse_args()

    store, handle = parse(a.product, a.store)
    p = fetch(store, handle)
    kind = a.playbook or overrides(p["handle"]).get("playbook") or pick_playbook(p)
    slug = f"shop-{re.sub(r'[^a-z0-9]+', '-', handle.lower())[:40].strip('-')}"
    spec, vo_lines = build_spec(p, kind, slug, a.account)
    spec_path = os.path.join(ROOT, "content", "ads", f"{slug}-trailer.json")
    with open(spec_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(json.dumps({"product": p["title"], "price": p["price"], "playbook": kind, "spec": spec_path,
                      "qr": p["checkout"]}, indent=2))
    if a.spec_only:
        return

    shots = make_shots(dict(PLAYBOOKS[kind]), p, os.path.join(ROOT, spec["shots_dir"]), a.seed)
    print(json.dumps({"shots": shots}))
    subprocess.run([sys.executable, os.path.join(HERE, "narrator.py"), os.path.join(ROOT, "assets", "voice", slug),
                    *vo_lines], check=True)

    import trailer
    os.makedirs(a.out, exist_ok=True)
    video = os.path.join(a.out, f"{slug}-ad.mp4")
    secs = trailer.build(spec, video)
    print(json.dumps({"video": video, "seconds": secs}))
    if a.post:
        subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "--account", a.account, "--platform", "instagram",
                        "--video", video, "--caption", spec["caption"] + "\n\n" + " ".join("#" + t for t in spec["hashtags"]),
                        "--mode", os.environ.get("IRUN_MODE", "live")], check=True)


if __name__ == "__main__":
    main()
