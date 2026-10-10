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


def write_script(product, angle, platform, cta, avoid_hooks=(), voice=None):
    key = os.environ["ANTHROPIC_API_KEY"]
    user = (
        f"Product: {product['name']}\nWhat it does: {product['pitch']}\nWho it's for: {product['audience']}\n"
        f"Angle for this video: {angle}\nPlatform: {platform}\nKeyword: {product['keyword']}\n"
        f"Call to action to use (spoken as last beat, adapted naturally): {cta}\n"
        + (f"Do not reuse these recent hooks: {list(avoid_hooks)}\n" if avoid_hooks else "")
    )
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 1200, "system": SYSTEM.replace("{voice}", voice or DEFAULT_VOICE), "messages": [{"role": "user", "content": user}]},
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0))
    beats = [re.sub(r"[^\x00-\x7F]+", "", b).strip() for b in data["beats"] if b.strip()]
    emph = data.get("emphasis") or []
    emph = (emph + [""] * len(beats))[: len(beats)]
    tags = [t.lstrip("#").replace(" ", "") for t in data.get("hashtags", [])][:6]
    return {"beats": beats, "emphasis": emph, "caption": data["caption"].strip(), "hashtags": tags}


FACELESS_SYSTEM = """You write faceless short-form vertical videos (TikTok / Reels / YouTube Shorts): a voiceover over a
sequence of AI-generated images, with captions. You are writing for this brand:
{voice}

Hard rules:
- 6 to 9 scenes. Each scene has "say" (one spoken sentence, 5-16 words) and "visual" (the picture for that line).
- 70-120 spoken words total. Scene 1 is a scroll-stopping hook under 10 words.
- "visual" is a concrete, filmable image description: subject, setting, light, mood. No text or words in the
  image, no logos, no brand names, no real or famous people, no children. Keep one consistent world across scenes.
- Only true statements. No invented statistics, no invented quotes, no made-up stories about real people,
  no income claims, no guarantees, no prices, no medical or legal advice.
- No emojis. No hashtags inside "say".
- The last scene's "say" is the call to action given to you, word for word.
Return ONLY JSON: {"title": "under 60 characters", "scenes": [{"say": "...", "visual": "..."}],
"caption": "1-3 sentences", "hashtags": ["4-6 tags without #"]}"""


def write_faceless(series, idea, cta, avoid_hooks=(), voice=None):
    """Claude turns an idea (or a series angle) into a faceless video script."""
    key = os.environ["ANTHROPIC_API_KEY"]
    user = (
        f"Series: {series['name']}\nWhat the series is about: {series['topic']}\nWho watches: {series['audience']}\n"
        f"Idea for this video: {idea}\nCall to action (last scene, word for word): {cta}\n"
        + (f"Do not reuse these recent hooks: {list(avoid_hooks)}\n" if avoid_hooks else "")
    )
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 2000, "system": FACELESS_SYSTEM.replace("{voice}", voice or DEFAULT_VOICE),
              "messages": [{"role": "user", "content": user}]},
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))
