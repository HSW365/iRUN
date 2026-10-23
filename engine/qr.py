"""Scan-to-subscribe QR: every iRun video ends with a QR code that opens the product's signup link."""
import io
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONTS = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
SECONDS = 4.0  # QR shows for the last SECONDS of the video


def link_for(acct, product_id=None):
    """The signup link for a product (falls back to the account's first product with a link)."""
    prods = acct.get("products") or []
    for p in prods:
        if product_id and p.get("id") == product_id and p.get("link"):
            return p["link"]
    return next((p["link"] for p in prods if p.get("link")), None)


def card(url, size=340, label="SCAN TO SUBSCRIBE"):
    import segno
    buf = io.BytesIO()
    segno.make(url, error="h").save(buf, kind="png", scale=20, border=0, dark="#0a0a0f", light="#ffffff")
    pad = 26
    code = Image.open(buf).convert("RGBA").resize((size - pad * 2, size - pad * 2), Image.NEAREST)
    try:
        f = ImageFont.truetype(os.path.join(FONTS, "BarlowCondensed-ExtraBold.ttf"), 46)
    except OSError:
        f = ImageFont.load_default()
    out = Image.new("RGBA", (size, size + 74), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=30, fill=(255, 255, 255, 255))
    out.alpha_composite(code, (pad, pad))
    tw = d.textlength(label, font=f)
    d.text(((size - tw) / 2, size + 14), label, font=f, fill=(34, 211, 238, 255))
    return out


def stamp(video, url, x="W-w-70", y="H-h-460"):
    """Overlay the QR card on the end of video in place. Returns True when it was added."""
    if not url:
        return False
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                                   capture_output=True, text=True, check=True).stdout.strip())
        work = tempfile.mkdtemp(prefix="irun-qr-")
        png = os.path.join(work, "qr.png")
        card(url).save(png)
        out = os.path.join(work, "out.mp4")
        start = max(0.0, dur - SECONDS)
        flt = (f"[1:v]format=rgba,fade=t=in:st={start:.2f}:d=0.4:alpha=1[q];"
               f"[0:v][q]overlay={x}:{y}:enable='gte(t,{start:.2f})',format=yuv420p[v]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-loop", "1", "-t", f"{dur:.2f}", "-i", png,
                        "-filter_complex", flt, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", "-c:a", "copy", "-movflags", "+faststart", out], check=True)
        os.replace(out, video)
        return True
    except Exception as e:  # a missing QR never blocks a post
        print(f"[qr] skipped: {e}")
        return False
