"""Shopify cover for the HSW365 Tear-Off Microfiber Roll: 2048x2048 studio card."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import microroll_render as R
from microroll_render import *

S = 2048


def cover(out):
    y, x = np.mgrid[0:S, 0:S]
    g = np.exp(-(((x - S * 0.5) / (S * 0.55)) ** 2 + ((y - S * 0.52) / (S * 0.42)) ** 2))[..., None]
    bg = np.array([8, 12, 16], np.float32) * (1 - g) + np.array([14, 58, 56], np.float32) * g
    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)
    # floor reflection band
    d.ellipse((260, 1440, 1788, 1600), fill=(0, 0, 0, 90))
    roll = R.roll(0.85).resize((1500, 1267), Image.LANCZOS)
    img.alpha_composite(roll, ((S - roll.width) // 2, 470))
    def c(yv, s, f, fill):
        d.text(((S - tw(f, s)) / 2, yv), s, font=f, fill=fill)
    c(110, "HSW365", M(70), (*TEAL, 255))
    c(200, "TEAR-OFF MICROFIBER ROLL", B(170), WHITE)
    c(400, "Rip. Wipe. Wash. Repeat.", I("InterDisplay-Medium.otf", 70), (210, 214, 222))
    pills = [("30 SHEETS", TEAL), ("WASH + REUSE", CYAN), ("LINT-FREE", GOLD)]
    f = I("Inter-SemiBold.otf", 58)
    ws = [int(tw(f, t)) + 110 for t, _ in pills]
    gx = (S - sum(ws) - 40 * 2) // 2
    for (t, col), w in zip(pills, ws):
        p = rrect((w, 130), 65, (*CARD, 255), (*col, 255), 5)
        ImageDraw.Draw(p).text((55, 30), t, font=f, fill=WHITE)
        img.alpha_composite(p, (gx, 1740)); gx += w + 40
    c(1920, "Kitchen  ·  Car  ·  Glass  ·  Garage", I("Inter-Medium.otf", 54), MUT)
    img.convert("RGB").save(out, quality=92)


if __name__ == "__main__":
    cover(sys.argv[1])
