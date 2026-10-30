"""ElevenLabs for iRun: one client for everything the ElevenLabs API does, used by the video, movie, ad and narrator
engines and runnable from the command line.

  Voice     tts (with optional word timings), voices, design a new voice, clone a voice, voice changer
  Audio     music, sound effects, audio isolation (pull vocals out of a song), dubbing
  Text      speech-to-text with word timings (lyrics), forced alignment (lyrics text -> exact timings)
  Visual    image and video generation (Image & Video API, Pro plan+), image + audio -> lip-synced performance
  Account   credits remaining (every engine checks this before spending)

Key: ELEVENLABS_API_KEY (repo secret). Voice: ELEVENLABS_VOICE_ID (optional; narrator uses ELEVENLABS_NARRATOR_VOICE_ID).

  python engine/elevenlabs.py credits
  python engine/elevenlabs.py voices
  python engine/elevenlabs.py tts "Line to say" out.mp3 [--voice ID]
  python engine/elevenlabs.py music "dark cinematic trailer score, hits and risers" out.mp3 --seconds 30
  python engine/elevenlabs.py sfx "crowd roar in a stadium" out.mp3 --seconds 5
  python engine/elevenlabs.py isolate song.mp3 vocals.mp3
  python engine/elevenlabs.py lyrics song.mp3 lyrics.json          # isolates the vocal first, then transcribes
  python engine/elevenlabs.py align song.mp3 lyrics.txt timed.json
  python engine/elevenlabs.py changer in.mp3 out.mp3 --voice ID
  python engine/elevenlabs.py clone "Hoodstar365" ref1.wav [ref2.wav ...]
  python engine/elevenlabs.py design "deep warm cinematic narrator, late 40s, American" "Sample line." outdir/
  python engine/elevenlabs.py dub video.mp4 es out_es.mp4
  python engine/elevenlabs.py image "prompt" out.png [--ref photo.jpg] [--model gemini-3-pro-image] [--aspect 9:16]
  python engine/elevenlabs.py video "prompt" out.mp4 [--start frame.png] [--seconds 8] [--model veo-3.1-fast-generate-001]
  python engine/elevenlabs.py perform photo.jpg vocal.mp3 out.mp4  # lip-synced performance (creatify-aurora)
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time

import requests

API = "https://api.elevenlabs.io"
TTS_MODEL = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
DEFAULT_VOICE = "pNInz6obpgDQGcFmaJgB"
IMAGE_MODEL = os.environ.get("ELEVENLABS_IMAGE_MODEL", "gemini-3-pro-image")
VIDEO_MODEL = os.environ.get("ELEVENLABS_VIDEO_MODEL", "veo-3.1-fast-generate-001")
LIPSYNC_MODEL = os.environ.get("ELEVENLABS_LIPSYNC_MODEL", "creatify-aurora")


class ElevenError(RuntimeError):
    pass


def log(*a):
    print("[elevenlabs]", *a, flush=True)


def enabled():
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def _key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        raise ElevenError("ELEVENLABS_API_KEY is not set")
    return k


def _req(method, path, *, json_body=None, data=None, files=None, params=None, stream=False, timeout=300, raw=False):
    hdr = {"xi-api-key": _key()}
    for attempt in range(4):
        r = requests.request(method, f"{API}{path}", headers=hdr, json=json_body, data=data, files=files,
                             params=params, stream=stream, timeout=timeout)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(8 * (attempt + 1))
            continue
        if not r.ok:
            try:
                d = r.json().get("detail", r.text)
            except ValueError:
                d = r.text
            raise ElevenError(f"{method} {path} HTTP {r.status_code}: {str(d)[:400]}")
        if raw or stream:
            return r
        ct = r.headers.get("content-type", "")
        return r.json() if "json" in ct else r.content
    raise ElevenError(f"{method} {path} kept failing")


def _save(content, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(content)
    return out


def _file(path):
    return (os.path.basename(path), open(path, "rb"), mimetypes.guess_type(path)[0] or "application/octet-stream")


# ---------------------------------------------------------------- account
def credits():
    """Credits left this period: {"used", "limit", "remaining", "tier"}."""
    s = _req("GET", "/v1/user/subscription")
    used, limit = int(s.get("character_count", 0)), int(s.get("character_limit", 0))
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "tier": s.get("tier")}


def require(min_credits, what="this"):
    c = credits()
    if c["remaining"] < min_credits:
        raise ElevenError(f"Not enough ElevenLabs credits for {what}: {c['remaining']:,} left, about "
                          f"{min_credits:,} needed (plan {c['tier']}).")
    return c


# ---------------------------------------------------------------- voice
def voices():
    return [{"id": v["voice_id"], "name": v["name"], "category": v.get("category"),
             "labels": v.get("labels", {})} for v in _req("GET", "/v1/voices").get("voices", [])]


def tts(text, out, voice=None, model=None, settings=None, timed=False):
    """Speech to out (mp3). timed=True also returns word timings [(start, end), ...]."""
    voice = voice or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    body = {"text": text, "model_id": model or TTS_MODEL,
            "voice_settings": settings or {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}}
    if not timed:
        return _save(_req("POST", f"/v1/text-to-speech/{voice}", json_body=body,
                          params={"output_format": "mp3_44100_128"}), out)
    d = _req("POST", f"/v1/text-to-speech/{voice}/with-timestamps", json_body=body)
    _save(base64.b64decode(d["audio_base64"]), out)
    al = d.get("alignment") or {}
    words, cur = [], None
    for ch, s, e in zip(al.get("characters", []), al.get("character_start_times_seconds", []),
                        al.get("character_end_times_seconds", [])):
        if ch.isspace():
            cur = None
        elif cur is None:
            cur = [s, e]
            words.append(cur)
        else:
            cur[1] = e
    return out, [(s, e) for s, e in words]


def changer(src, out, voice=None, model="eleven_multilingual_sts_v2"):
    """Voice changer: same performance, different voice."""
    voice = voice or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    return _save(_req("POST", f"/v1/speech-to-speech/{voice}", data={"model_id": model},
                      files={"audio": _file(src)}, params={"output_format": "mp3_44100_128"}), out)


def clone(name, samples, description=""):
    """Instant voice clone from one or more clean recordings. Returns the new voice_id."""
    files = [("files", _file(p)) for p in samples]
    d = _req("POST", "/v1/voices/add", data={"name": name, "description": description}, files=files)
    return d["voice_id"]


def design(description, sample_text, outdir):
    """Design brand-new voices from a description. Writes preview mp3s; returns [{"generated_voice_id", "file"}]."""
    d = _req("POST", "/v1/text-to-voice/design",
             json_body={"voice_description": description, "text": sample_text, "model_id": "eleven_ttv_v3"})
    os.makedirs(outdir, exist_ok=True)
    res = []
    for i, p in enumerate(d.get("previews", []), 1):
        f = _save(base64.b64decode(p["audio_base_64"]), os.path.join(outdir, f"preview{i}.mp3"))
        res.append({"generated_voice_id": p["generated_voice_id"], "file": f})
    return res


def save_designed(name, description, generated_voice_id):
    d = _req("POST", "/v1/text-to-voice", json_body={"voice_name": name, "voice_description": description,
                                                     "generated_voice_id": generated_voice_id})
    return d["voice_id"]


# ---------------------------------------------------------------- audio
def music(prompt, out, seconds=30, model="music_v1"):
    ms = int(max(10, min(300, seconds)) * 1000)
    return _save(_req("POST", "/v1/music", json_body={"prompt": prompt, "music_length_ms": ms, "model_id": model},
                      params={"output_format": "mp3_44100_128"}, timeout=600), out)


def sfx(prompt, out, seconds=None, influence=0.5):
    body = {"text": prompt, "prompt_influence": influence}
    if seconds:
        body["duration_seconds"] = max(0.5, min(30, float(seconds)))
    return _save(_req("POST", "/v1/sound-generation", json_body=body), out)


def isolate(src, out):
    """Strip the beat/background and keep the voice (vocals out of a finished song)."""
    return _save(_req("POST", "/v1/audio-isolation", files={"audio": _file(src)}, timeout=900), out)


def dub(src, target_lang, out, source_lang="auto", poll=15, timeout=3600):
    d = _req("POST", "/v1/dubbing", data={"target_lang": target_lang, "source_lang": source_lang},
             files={"file": _file(src)})
    did, t0 = d["dubbing_id"], time.time()
    while True:
        time.sleep(poll)
        st = _req("GET", f"/v1/dubbing/{did}").get("status")
        if st == "dubbed":
            break
        if st in ("failed", "error") or time.time() - t0 > timeout:
            raise ElevenError(f"dubbing {did} {st}")
    return _save(_req("GET", f"/v1/dubbing/{did}/audio/{target_lang}", raw=True).content, out)


# ---------------------------------------------------------------- text
def stt(src, diarize=False, lang=None):
    """Speech-to-text with word timings: {"text", "words": [{"text", "start", "end"}]}."""
    data = {"model_id": "scribe_v1", "diarize": str(diarize).lower(), "timestamps_granularity": "word"}
    if lang:
        data["language_code"] = lang
    d = _req("POST", "/v1/speech-to-text", data=data, files={"file": _file(src)}, timeout=900)
    words = [{"text": w["text"], "start": w["start"], "end": w["end"]}
             for w in d.get("words", []) if w.get("type", "word") == "word"]
    return {"text": d.get("text", ""), "language": d.get("language_code"), "words": words}


def align(src, text):
    """Forced alignment: known lyrics/script + the audio -> exact word timings (much cheaper than transcribing)."""
    d = _req("POST", "/v1/forced-alignment", data={"text": text}, files={"file": _file(src)}, timeout=900)
    return {"text": text, "words": [{"text": w["text"], "start": w["start"], "end": w["end"]}
                                    for w in d.get("words", [])]}


def lyrics(song, work, text=None):
    """Timed lyrics for a song, cached in work/lyrics.json. With the lyric text it uses forced alignment; without
    it, it isolates the vocal and transcribes it."""
    os.makedirs(work, exist_ok=True)
    cache = os.path.join(work, "lyrics.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    vocal = os.path.join(work, "vocal.mp3")
    if not os.path.exists(vocal):
        try:
            isolate(song, vocal)
        except ElevenError as e:
            log("isolation failed, using the full mix:", e)
            vocal = song
    res = align(vocal, text) if text else stt(vocal)
    json.dump(res, open(cache, "w"), indent=1)
    return res


def lines_between(ly, t0, t1):
    """The words sung between t0 and t1 seconds (song time)."""
    return " ".join(w["text"] for w in (ly or {}).get("words", []) if w["end"] > t0 and w["start"] < t1).strip()


# ---------------------------------------------------------------- image + video (Image & Video API)
def ref_file(path, mime=None):
    """Inline reference (<=25MB) for image/video/audio inputs."""
    mime = mime or mimetypes.guess_type(path)[0] or "application/octet-stream"
    if mime == "audio/mp3":
        mime = "audio/mpeg"
    return {"type": "inline_base64", "content_base64": base64.b64encode(open(path, "rb").read()).decode(),
            "mime_type": mime}


def ref_gen(generation_id):
    return {"type": "generation", "generation_id": generation_id}


def ref_asset(asset_id):
    return {"type": "asset", "asset_id": asset_id}


def upload(path, name=None):
    d = _req("POST", "/v1/assets", data={"name": name or os.path.basename(path)}, files={"asset": _file(path)})
    return d["asset_id"]


def _wait(kind, gid, every, timeout):
    t0 = time.time()
    while True:
        time.sleep(every)
        g = _req("GET", f"/v1/flows/{kind}/{gid}")
        st = g.get("status")
        if st == "completed":
            return g
        if st == "failed":
            raise ElevenError(f"{kind} {gid} failed: {g.get('failure_reason')} {g.get('failure_message', '')}")
        if time.time() - t0 > timeout:
            raise ElevenError(f"{kind} {gid} timed out")
        every = min(every * 1.3, 30)


def _generate(kind, body, out, every, timeout):
    meta = out + ".gen"
    if os.path.exists(out) and os.path.getsize(out) > 1000 and os.path.exists(meta):
        return open(meta).read().strip()
    g = _req("POST", f"/v1/flows/{kind}", json_body=body)
    log(kind, body.get("model_id"), "->", g["id"])
    g = _wait(kind, g["id"], every, timeout)
    r = requests.get(g["content_url"], timeout=600)
    r.raise_for_status()
    _save(r.content, out)
    open(meta, "w").write(g["id"])
    return g["id"]


def image(prompt, out, refs=None, model=None, aspect="9:16", resolution="2K"):
    """Generate an image; refs = list of reference objects (ref_file / ref_gen / ref_asset). Returns generation id."""
    body = {"model_id": model or IMAGE_MODEL, "prompt": prompt, "aspect_ratio": aspect, "resolution": resolution}
    if refs:
        body["images"] = refs
    return _generate("image", body, out, 2, 900)


def video(prompt, out, start=None, seconds=8, model=None, aspect="9:16", resolution="1080p", audio=False,
          refs=None):
    """Generate a video clip; start = reference object for the first frame. Returns generation id."""
    m = model or VIDEO_MODEL
    body = {"model_id": m, "prompt": prompt, "aspect_ratio": aspect, "resolution": resolution}
    if m.startswith("veo"):
        body["duration_secs"] = min((4, 6, 8), key=lambda d: abs(d - seconds))
        body["generate_audio"] = bool(audio)
    else:
        body["duration_secs"] = int(max(4, min(15, round(seconds))))
    if start:
        body["start_frame"] = start
    elif refs:
        body["images"] = refs
    return _generate("video", body, out, 10, 1800)


def perform(image_ref, audio_ref, out, model=None, resolution="720p"):
    """Lip-synced performance: a still of the artist + a vocal slice -> the artist singing those words."""
    body = {"model_id": model or LIPSYNC_MODEL, "image": image_ref, "audio": audio_ref, "resolution": resolution}
    return _generate("video", body, out, 10, 1800)


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("credits")
    sp.add_parser("voices")
    p = sp.add_parser("tts"); p.add_argument("text"); p.add_argument("out"); p.add_argument("--voice")
    p = sp.add_parser("music"); p.add_argument("prompt"); p.add_argument("out"); p.add_argument("--seconds", type=float, default=30)
    p = sp.add_parser("sfx"); p.add_argument("prompt"); p.add_argument("out"); p.add_argument("--seconds", type=float)
    p = sp.add_parser("isolate"); p.add_argument("src"); p.add_argument("out")
    p = sp.add_parser("lyrics"); p.add_argument("song"); p.add_argument("out"); p.add_argument("--text-file")
    p = sp.add_parser("align"); p.add_argument("src"); p.add_argument("text_file"); p.add_argument("out")
    p = sp.add_parser("changer"); p.add_argument("src"); p.add_argument("out"); p.add_argument("--voice")
    p = sp.add_parser("clone"); p.add_argument("name"); p.add_argument("samples", nargs="+")
    p = sp.add_parser("design"); p.add_argument("description"); p.add_argument("text"); p.add_argument("outdir")
    p = sp.add_parser("dub"); p.add_argument("src"); p.add_argument("lang"); p.add_argument("out")
    p = sp.add_parser("image"); p.add_argument("prompt"); p.add_argument("out"); p.add_argument("--ref", action="append")
    p.add_argument("--model"); p.add_argument("--aspect", default="9:16")
    p = sp.add_parser("video"); p.add_argument("prompt"); p.add_argument("out"); p.add_argument("--start")
    p.add_argument("--seconds", type=float, default=8); p.add_argument("--model"); p.add_argument("--aspect", default="9:16")
    p.add_argument("--audio", action="store_true")
    p = sp.add_parser("perform"); p.add_argument("photo"); p.add_argument("vocal"); p.add_argument("out")
    a = ap.parse_args()
    c = a.cmd
    if c == "credits":
        print(json.dumps(credits(), indent=2))
    elif c == "voices":
        for v in voices():
            print(f"{v['id']}  {v['name']}  {v['category']}  {json.dumps(v['labels'])}")
    elif c == "tts":
        print(tts(a.text, a.out, a.voice))
    elif c == "music":
        print(music(a.prompt, a.out, a.seconds))
    elif c == "sfx":
        print(sfx(a.prompt, a.out, a.seconds))
    elif c == "isolate":
        print(isolate(a.src, a.out))
    elif c == "lyrics":
        work = os.path.dirname(os.path.abspath(a.out))
        txt = open(a.text_file).read() if a.text_file else None
        ly = lyrics(a.song, work, txt)
        json.dump(ly, open(a.out, "w"), indent=1)
        print(ly["text"])
    elif c == "align":
        json.dump(align(a.src, open(a.text_file).read()), open(a.out, "w"), indent=1)
        print(a.out)
    elif c == "changer":
        print(changer(a.src, a.out, a.voice))
    elif c == "clone":
        print(clone(a.name, a.samples))
    elif c == "design":
        print(json.dumps(design(a.description, a.text, a.outdir), indent=2))
    elif c == "dub":
        print(dub(a.src, a.lang, a.out))
    elif c == "image":
        print(image(a.prompt, a.out, [ref_file(r) for r in (a.ref or [])], a.model, a.aspect))
    elif c == "video":
        print(video(a.prompt, a.out, ref_file(a.start) if a.start else None, a.seconds, a.model, a.aspect,
                    audio=a.audio))
    elif c == "perform":
        print(perform(ref_file(a.photo), ref_file(a.vocal, "audio/mpeg"), a.out))


if __name__ == "__main__":
    try:
        main()
    except ElevenError as e:
        sys.exit(f"[elevenlabs] {e}")
