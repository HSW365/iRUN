"""Canva render step for iRun trailer ads.

iRun's shots come from Canva's image generator (photoreal, no watermark, full 1080x1920). Canva runs through the
Canva connector in iRun's daily Claude writer session (GitHub Actions has no Canva login), in this order:

  1. generate-image, aspectRatio PORTRAIT_9_16, once per shot (cinematic still prompt, no text). Poll
     get-generate-image-job; keep each media id. Content filters refuse images of children alone: put a child
     only in a shot with a parent, or leave them out.
  2. create-design "blank plain black vertical Instagram Story" -> design id. read-design with open_transaction.
     edit-design: insert_fill the first media on page 1 at top 0 left 0 width 1080 height 1920, add_page (1080x1920)
     once per remaining shot, then insert_fill one media per page. Commit.
  3. export-design png, export_quality "pro", width 1080, height 1920 -> one signed URL per page (in page order).
  4. python engine/canva_shots.py content/shots/<slug> name1=URL1 name2=URL2 ...   (this file)
     Downloads every page, fits it to 1080x1920 and saves content/shots/<slug>/<name>.jpg for engine/trailer.py.

  python engine/canva_shots.py content/shots/dispute365-denied man=https://... stamp=https://...
"""
import io
import os
import sys

import requests
from PIL import Image

W, H = 1080, 1920


def fit(img):
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x0 = (img.width - W) // 2; y0 = (img.height - H) // 2
    return img.crop((x0, y0, x0 + W, y0 + H))


def save(outdir, pairs):
    os.makedirs(outdir, exist_ok=True)
    done = []
    for name, url in pairs:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        path = os.path.join(outdir, f"{name}.jpg")
        fit(img).save(path, quality=93)
        done.append(path)
        print(f"[canva] {name}: {img.size[0]}x{img.size[1]} -> {path}")
    return done


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    save(sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]])
