"""Script writer: Claude turns a product + angle into a short-form video script."""
import json
import os
import re
import requests

MODEL = os.environ.get("IRUN_MODEL", "claude-sonnet-5-5")

DEFAULT_VOICE = ("HSW365 Media, run by Hoodstar365: a solo founder and U.S. Army veteran whose philosophy is "
                 "\"Turn Negative Into Positive\". Direct, confident, street-smart, motivational, no corporate fluff.")

SYSTEM = """You write short-form vertical video scripts (TikTok / Instagram Reels) for this brand:
{voice}

Hard rules:
- 45-75 spoken words total. First beat is a scroll-stopping hook under 9 words.
- 5 to 7 beats. Each beat is one short on-screen line (max 9 words) that is ALSO spoken.
- No prices, no discounts, no income claims, no guarantees, no fake testimonials, no fake statistics.
- Only describe what the product actually does per the pitch given. Do not invent features.
- No emojis anywhere. No hashtags inside beats.
- The last beat is the call to action and must contain the keyword in capitals.
Return ONLY JSON: {"beats": [..], "emphasis": [one word from each beat to highlight, same length as beats],
"caption": "...", "hashtags": ["..."]}.
Caption: 1-3 sentences, ends with the CTA line provided. 4-6 relevant hashtags without the # sign."""


def ask_json(system, user, max_tokens=1200):
    """One Claude call that must answer with a JSON object."""
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"writer returned no JSON: {text[:200]}")
    return json.loads(m.group(0))


def write_script(product, angle, platform, cta, avoid_hooks=(), voice=None, focus=None, winning_hooks=(), fmt="video"):
    """focus: this week's goal from the 30-day plan. winning_hooks: hooks that scored best so far (style reference).
    fmt 'carousel' asks for swipeable slides instead of spoken beats (same JSON shape)."""
    user = (
        f"Product: {product['name']}\nWhat it does: {product['pitch']}\nWho it's for: {product['audience']}\n"
        f"Angle for this video: {angle}\nPlatform: {platform}\nKeyword: {product['keyword']}\n"
        f"Call to action to use (spoken as last beat, adapted naturally): {cta}\n"
        + (f"This week's goal: {focus}\n" if focus else "")
        + (f"Do not reuse these recent hooks: {list(avoid_hooks)}\n" if avoid_hooks else "")
        + (f"These hooks performed best so far. Match their style, do not copy them: {list(winning_hooks)}\n"
           if winning_hooks else "")
        + ("Format: Instagram carousel. Each beat is one swipeable slide, read not spoken. "
           "First slide is the hook, last slide is the call to action.\n" if fmt == "carousel" else "")
    )
    data = ask_json(SYSTEM.replace("{voice}", voice or DEFAULT_VOICE), user)
    beats = [re.sub(r"[^\x00-\x7F]+", "", b).strip() for b in data["beats"] if b.strip()]
    emph = data.get("emphasis") or []
    emph = (emph + [""] * len(beats))[: len(beats)]
    tags = [t.lstrip("#").replace(" ", "") for t in data.get("hashtags", [])][:6]
    return {"beats": beats, "emphasis": emph, "caption": data["caption"].strip(), "hashtags": tags}
