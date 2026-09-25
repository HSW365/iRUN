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
