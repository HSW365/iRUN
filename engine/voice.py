"""Voiceover: ElevenLabs when a key is set, otherwise free Microsoft neural voices via edge-tts."""
import asyncio
import os
import subprocess
import requests


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _eleven(text, out):
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = os.environ.get("ELEVENLABS_VOICE_ID") or "pNInz6obpgDQGcFmaJgB"
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        json={"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}},
        timeout=120,
    )
    r.raise_for_status()
    with open(out, "wb") as f:
        f.write(r.content)


def _edge(text, out):
    import edge_tts
    voice = os.environ.get("IRUN_EDGE_VOICE", "en-US-AndrewMultilingualNeural")
    asyncio.run(edge_tts.Communicate(text, voice, rate="+8%").save(out))


def speak(text, out):
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            _eleven(text, out)
            return out, duration(out), "elevenlabs"
        except Exception as e:  # fall back rather than miss the slot
            print(f"[voice] ElevenLabs failed ({e}); falling back to edge-tts")
    _edge(text, out)
    return out, duration(out), "edge-tts"


# ---- word-timed speech (for burned-in word captions in faceless videos) ----

def _eleven_timed(text, out):
    import base64
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = os.environ.get("ELEVENLABS_VOICE_ID") or "pNInz6obpgDQGcFmaJgB"
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        headers={"xi-api-key": key},
        json={"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    with open(out, "wb") as f:
        f.write(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or {}
    chars, starts, ends = al.get("characters", []), al.get("character_start_times_seconds", []), \
        al.get("character_end_times_seconds", [])
    words, cur = [], None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            cur = None
        elif cur is None:
            cur = [s, e]
            words.append(cur)
        else:
            cur[1] = e
    return [(s, e) for s, e in words]


def _edge_timed(text, out):
    import edge_tts
    voice = os.environ.get("IRUN_EDGE_VOICE", "en-US-AndrewMultilingualNeural")
    kw = {"rate": "+8%", "proxy": os.environ.get("HTTPS_PROXY") or None}

    async def go():
        try:
            com = edge_tts.Communicate(text, voice, boundary="WordBoundary", **kw)
        except TypeError:  # older edge-tts sends word boundaries by default
            com = edge_tts.Communicate(text, voice, **kw)
        marks = []
        with open(out, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    marks.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7))
        return marks

    return asyncio.run(go())


def spread(n, length, lead=0.05):
    """Even-ish word timings when the voice engine gave none (or a count that doesn't match the text)."""
    if n <= 0:
        return []
    step = max(length - lead, 0.1) / n
    return [(lead + i * step, lead + (i + 1) * step) for i in range(n)]


def speak_timed(text, out):
    """Speak text. Returns (path, seconds, source, [(start, end) per whitespace-separated word])."""
    n = len(text.split())
    marks, src = None, "edge-tts"
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            marks, src = _eleven_timed(text, out), "elevenlabs"
        except Exception as e:
            print(f"[voice] ElevenLabs failed ({e}); falling back to edge-tts")
    if marks is None:
        marks = _edge_timed(text, out)
    length = duration(out)
    if len(marks) != n:  # e.g. "24/7" spoken as several words: keep captions in step by spreading evenly
        marks = spread(n, length)
    return out, length, src, marks
