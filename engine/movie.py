"""iRun Movie: turns a shot list into a real AI-filmed episode (moving footage, characters speaking on camera,
narrator, score, location supers, subtitles, end card). Built for the Hoodlum Soldier series; works for any
series folder in content/movie/<series>/ that has cast.json + episodes.json.

Per shot:
  1. start frame   identity-locked still (cast reference portraits passed as references) - IRUN_MOVIE_IMAGE_MODEL
  2. motion        image-to-video from that frame. "talk" shots use a model that generates synced dialogue audio
                   (IRUN_MOVIE_TALK_MODEL, lip-synced lines); other shots use IRUN_MOVIE_BROLL_MODEL
  3. narrator      "vo" lines in Ali's older voice (engine/narrator.py, open-source Kokoro, free)
Episode: graded 1080x1920 cut, cold open -> title card -> scenes -> end card (next episode + QR), score bed
(IRUN_MOVIE_SCORE_MODEL) ducked under dialogue and narration, burned subtitles for spoken lines.

All generation goes through Pollinations (POLLINATIONS_TOKEN). Results are cached in the work dir and the
server joins identical requests, so a re-run doesn't pay twice.

  python engine/movie.py hoodlum-soldier 2 out/ep02.mp4 [--work work/]
Writes the mp4, a poster jpg next to it, and <out>.json (shot log: models used, fallbacks, cost estimate).
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import wave

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")
API = "https://gen.pollinations.ai"
MEDIA = "https://media.pollinations.ai"
W, H, FPS = 1080, 1920, 30
IMAGE_MODEL = os.environ.get("IRUN_MOVIE_IMAGE_MODEL", "google/gemini-nano-banana-2.1")
TALK_MODEL = os.environ.get("IRUN_MOVIE_TALK_MODEL", "google/veo-3.1-fast")
BROLL_MODEL = os.environ.get("IRUN_MOVIE_BROLL_MODEL", "bytedance/seedance-1-pro-fast")
FALLBACK_VIDEO = [m for m in os.environ.get("IRUN_MOVIE_FALLBACK_MODELS",
                  "alibaba/wan-2.6,x-ai/grok-imagine-video,prunaai/p-video").split(",") if m]
SCORE_MODEL = os.environ.get("IRUN_MOVIE_SCORE_MODEL", "stability-ai/stable-audio-3-medium")
TALK_DURS = (4, 6, 8)  # veo durations
RED = (214, 32, 39)
GRADE = {  # ffmpeg colour per grade id in cast.json
    "street": "eq=contrast=1.12:saturation=0.85:brightness=-0.03,colorbalance=bs=0.08:bm=0.04:rh=0.05:rm=0.03",
    "camp": "eq=contrast=1.08:saturation=0.8,colorbalance=rm=0.05:gm=0.03:bm=-0.06",
    "war": "eq=contrast=1.15:saturation=0.75:brightness=0.02,colorbalance=rm=0.08:gm=0.03:bm=-0.1:rh=0.05",
    "home": "eq=contrast=1.06:saturation=0.7:brightness=-0.02,colorbalance=bs=0.07:bm=0.05",
    "healing": "eq=contrast=1.05:saturation=1.0,colorbalance=rm=0.06:gm=0.02:bm=-0.05:rh=0.04",
}


def log(*a):
    print("[movie]", *a, flush=True)


def _key():
    k = os.environ.get("POLLINATIONS_TOKEN") or os.environ.get("POLLINATIONS_KEY")
    if not k:
        raise SystemExit("POLLINATIONS_TOKEN is not set")
    return k


def _auth():
    return {"Authorization": f"Bearer {_key()}"}


def _h(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def balance():
    try:
        r = requests.get(f"{API}/account/balance", headers=_auth(), timeout=30)
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def media_job(kind, prompt, params, out, timeout=1500):
    """Generate one media file (kind = image | video | audio) with the async job API, save it to out.
    Returns the public media URL when the server gives one."""
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        meta = out + ".url"
        return open(meta).read().strip() if os.path.exists(meta) else None
    url = f"{API}/{kind}/{urllib.parse.quote(prompt, safe='')}"
    hdr = {**_auth(), "Prefer": "respond-async"}
    for attempt in range(3):
        r = requests.get(url, params=params, headers=hdr, timeout=300)
        if r.status_code == 200 and len(r.content) > 1000:  # cached result came back directly
            open(out, "wb").write(r.content)
            link = _link(r)
            if link:
                open(out + ".url", "w").write(link)
            return link
        if r.status_code in (200, 202):
            job = r.json()
            break
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(15 * (attempt + 1))
            continue
        raise RuntimeError(f"{kind} {params.get('model')} HTTP {r.status_code}: {r.text[:300]}")
    jid = job.get("id")
    t0 = time.time()
    while True:
        time.sleep(6)
        s = requests.get(f"{API}/v1/jobs/{jid}", headers=_auth(), timeout=60).json()
        st = s.get("status")
        if st == "succeeded":
            break
        if st == "failed":
            raise RuntimeError(f"{kind} {params.get('model')} job failed: {json.dumps(s)[:400]}")
        if time.time() - t0 > timeout:
            raise RuntimeError(f"{kind} {params.get('model')} job timed out")
    res = requests.get(f"{API}/v1/jobs/{jid}/result", headers=_auth(), timeout=300, allow_redirects=True)
    if res.status_code != 200 or len(res.content) < 1000:
        ru = s.get("result_url")
        res = requests.get(ru, timeout=300) if ru else res
    if res.status_code != 200:
        raise RuntimeError(f"{kind} result HTTP {res.status_code}")
    open(out, "wb").write(res.content)
    link = s.get("result_url") or _link(res)
    if link and link.startswith(MEDIA):
        open(out + ".url", "w").write(link)
        return link
    return None


def _link(r):
    m = re.search(r"<(https://media\.pollinations\.ai/[^>]+)>", r.headers.get("Link", ""))
    return m.group(1) if m else None


def public_url(path):
    """A public URL for a local file (uploads to Pollinations media storage once)."""
    meta = path + ".url"
    if os.path.exists(meta):
        return open(meta).read().strip()
    ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4",
             "mp3": "audio/mpeg", "wav": "audio/wav"}[path.rsplit(".", 1)[-1].lower()]
    for attempt in range(3):
        with open(path, "rb") as f:
            r = requests.post(f"{MEDIA}/upload", data=f, timeout=600,
                              headers={**_auth(), "Content-Type": ctype, "X-File-Name": os.path.basename(path)})
        if r.ok:
            j = r.json()
            u = j.get("url") or f"{MEDIA}/{j['id']}"
            open(meta, "w").write(u)
            return u
        time.sleep(10)
    raise RuntimeError(f"upload failed {r.status_code}: {r.text[:200]}")


# ---------------------------------------------------------------- prompts
def speakers(s, cast):
    """'id: line | id: line' -> [(label, line)]"""
    out = []
    for part in s.split("|"):
        if ":" in part:
            who, line = part.split(":", 1)
            out.append((who.strip(), line.strip()))
        else:
            out.append(("", part.strip()))
    return out


def who_desc(who, cast):
    base = who.split("(")[0].strip()
    if base in cast["cast"]:
        return _short(cast["cast"][base])
    return who  # e.g. "mom (voicemail, off screen)", "kid (off screen)"


def _short(desc):
    return desc.split(",")[0]


def frame_prompt(shot, cast):
    people = "; ".join(cast["cast"][c] for c in shot.get("c", []))
    g = cast["grades"][shot["g"]]
    p = f"Cinematic film still from the prestige drama {cast['film']}. {shot['v']}."
    if people:
        p += f" Characters: {people}. Keep each character's face exactly like their reference photo."
    p += f" {g}. {cast['look']}. Photorealistic, real actors, no text, no captions, no watermark, no logos."
    return p


def motion_prompt(shot, cast, talk):
    g = cast["grades"][shot["g"]]
    p = f"{shot['v']}. Realistic cinematic movement, natural acting, subtle handheld camera. {g}. {cast['look']}."
    if talk:
        lines = speakers(shot["s"], cast)
        said = " ".join(
            (f'{who_desc(w, cast)} says, clearly and naturally: "{t}"' if "off screen" not in w and "on the line" not in w
             else f'An off-screen voice ({w.split("(")[0].strip()}) is heard saying: "{t}"')
            for w, t in lines)
        p += (f" Dialogue: {said} The speaking character's lips move in sync with the words."
              " Realistic ambient room sound. No music, no subtitles, no on-screen text.")
    else:
        p += " No people talking, no text on screen."
    return p


# ---------------------------------------------------------------- generation
def cast_refs(series_dir, cast, ids=None, work="."):
    """Reference portrait per cast id (generated once, kept in content/movie/<series>/refs.json)."""
    refs_path = os.path.join(series_dir, "refs.json")
    refs = json.load(open(refs_path)) if os.path.exists(refs_path) else {}
    os.makedirs(work, exist_ok=True)
    for cid in (ids if ids is not None else list(cast["cast"])):
        if cid in refs:
            continue
        desc = cast["cast"][cid]
        prompt = (f"Casting headshot photo of an actor playing {desc}. Front facing, neutral expression, head and"
                  f" shoulders, soft key light, plain dark grey studio background, photorealistic, 85mm, sharp focus,"
                  f" no text")
        params = {"model": IMAGE_MODEL, "width": 1024, "height": 1024, "seed": 365}
        base = cast.get("same_person", {}).get(cid)  # e.g. every older Ali is the teen Ali, aged
        if base:
            if base not in refs:
                cast_refs(series_dir, cast, [base], work)
                refs = json.load(open(refs_path))
            params["image"] = refs[base]
            prompt = (f"The exact same person as in the reference photo, same face, same bone structure, same scar,"
                      f" now shown as {desc}. " + prompt)
        out = os.path.join(work, f"ref_{cid}.jpg")
        u = media_job("image", prompt, params, out)
        refs[cid] = u or public_url(out)
        json.dump(refs, open(refs_path, "w"), indent=2)
        log("cast ref", cid, refs[cid])
    return refs


def make_frame(shot, cast, refs, work, seed):
    prompt = frame_prompt(shot, cast)
    out = os.path.join(work, f"frame_{_h(prompt, IMAGE_MODEL, seed)}.jpg")
    params = {"model": IMAGE_MODEL, "width": 1080, "height": 1920, "aspectRatio": "9:16", "seed": seed}
    imgs = [refs[c] for c in shot.get("c", []) if c in refs][:4]
    if imgs:
        params["image"] = "|".join(imgs)
    try:
        u = media_job("image", prompt, params, out)
    except Exception as e:  # noqa: BLE001
        log("frame retry without refs:", e)
        params.pop("image", None)
        u = media_job("image", prompt, params, out)
    return out, (u or public_url(out))


def make_clip(shot, cast, frame_url, work, seed, dur):
    talk = shot["t"] == "talk"
    prompt = motion_prompt(shot, cast, talk)
    models = [TALK_MODEL if talk else BROLL_MODEL] + FALLBACK_VIDEO
    errs = []
    for m in models:
        d = dur
        if m == TALK_MODEL and talk:
            d = next((x for x in TALK_DURS if x >= dur), TALK_DURS[-1])
        params = {"model": m, "image": frame_url, "duration": int(math.ceil(d)), "aspectRatio": "9:16",
                  "resolution": "720p", "seed": seed}
        if talk or m == TALK_MODEL:
            params["audio"] = "true"
        out = os.path.join(work, f"clip_{_h(prompt, params)}.mp4")
        try:
            media_job("video", prompt, params, out)
            if probe_dur(out) < 1.0:
                raise RuntimeError("empty clip")
            return out, m, errs
        except Exception as e:  # noqa: BLE001
            errs.append(f"{m}: {e}")
            log("clip fallback", m, str(e)[:200])
    return None, None, errs


def narrate(lines, outdir):
    """Narrator wavs (cached by text)."""
    import narrator
    todo = [t for t in lines if not os.path.exists(os.path.join(outdir, f"n_{_h(t)}.wav"))]
    if todo:
        tmp = os.path.join(outdir, "_n")
        narrator.main(tmp, todo)
        for i, t in enumerate(todo, 1):
            os.replace(os.path.join(tmp, f"vo{i}.wav"), os.path.join(outdir, f"n_{_h(t)}.wav"))
    return {t: os.path.join(outdir, f"n_{_h(t)}.wav") for t in lines}


def make_score(ep, total, work):
    mood = {1: "dark tense urban", 6: "war tension, pounding", 9: "war tension, dread", 10: "tragic, war",
            11: "grief, solemn", 12: "lonely, cold", 14: "haunted, nightmares"}
    m = mood.get(ep["n"], "hopeful, rising, emotional" if ep["n"] >= 15 else "tense, determined, gritty")
    prompt = (f"Cinematic orchestral film score for a prestige drama, {m}. Low strings, deep piano notes, subtle"
              f" pulsing percussion, slow build, no vocals, no lyrics.")
    out = os.path.join(work, f"score_{ep['n']}_{int(total)}.mp3")
    try:
        media_job("audio", prompt, {"model": SCORE_MODEL, "duration": int(min(180, total + 4)), "seed": ep["n"]}, out)
        return out
    except Exception as e:  # noqa: BLE001
        log("score fallback (synth drone):", e)
        out = os.path.join(work, f"score_{ep['n']}.wav")
        sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"sine=f=55:d={total+4},volume=0.35", "-f", "lavfi", "-i", f"sine=f=82.4:d={total+4},volume=0.2",
            "-f", "lavfi", "-i", f"anoisesrc=d={total+4}:c=brown:a=0.02",
            "-filter_complex", "amix=inputs=3,lowpass=f=900,tremolo=f=0.15:d=0.4", "-ar", "48000", out])
        return out


# ---------------------------------------------------------------- text overlays
def F(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def overlay_png(path, sub=None, loc=None):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if loc:
        f = F("SpaceMono-Bold.ttf", 34)
        d.text((72, 260), loc, font=f, fill=(245, 246, 250, 235), stroke_width=2, stroke_fill=(0, 0, 0, 160))
        d.rectangle((72, 312, 72 + 90, 316), fill=RED + (255,))
    if sub:
        f = F("BarlowCondensed-SemiBold.ttf", 58)
        lines = wrap(sub, f, W - 180)
        y = H - 430 - (len(lines) - 1) * 66
        for ln in lines:
            tw = d.textlength(ln, font=f)
            d.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255, 255), stroke_width=4,
                   stroke_fill=(0, 0, 0, 220))
            y += 66
    im.save(path)


def wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.getlength(t) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def title_card(path, cast, ep):
    im = Image.new("RGB", (W, H), (6, 6, 9))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-200, 640, W + 200, 1300), fill=(90, 8, 12))
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(160)), 0.85)
    d = ImageDraw.Draw(im)
    big = F("BarlowCondensed-ExtraBold.ttf", 200)
    for i, word in enumerate(cast["film"].split()):
        tw = d.textlength(word, font=big)
        d.text(((W - tw) / 2, 700 + i * 190), word, font=big, fill=(245, 246, 250), stroke_width=3,
               stroke_fill=RED)
    small = F("SpaceMono-Bold.ttf", 36)
    line = f"EPISODE {ep['n']}  /  {ep['title'].upper()}"
    tw = d.textlength(line, font=small)
    d.text(((W - tw) / 2, 1130), line, font=small, fill=(220, 220, 228))
    im.save(path)


def end_card(path, cast, ep, follow, link):
    import qr
    im = Image.new("RGB", (W, H), (6, 6, 9))
    d = ImageDraw.Draw(im)
    big = F("BarlowCondensed-ExtraBold.ttf", 150)
    for i, word in enumerate(cast["film"].split()):
        tw = d.textlength(word, font=big)
        d.text(((W - tw) / 2, 300 + i * 140), word, font=big, fill=(245, 246, 250), stroke_width=2,
               stroke_fill=RED)
    sm = F("SpaceMono-Bold.ttf", 34)
    mid = F("BarlowCondensed-SemiBold.ttf", 64)
    nxt = (f"EPISODE {ep['n'] + 1}: {ep['next'].upper()}" if ep.get("next") else "THE END")
    sub = "IN 48 HOURS" if ep.get("next") else "THANK YOU FOR WATCHING"
    for txt, f, y, col in ((nxt, mid, 640, (245, 246, 250)), (sub, sm, 730, RED)):
        tw = d.textlength(txt, font=f)
        d.text(((W - tw) / 2, y), txt, font=f, fill=col)
    card = qr.card(link, size=420, label="SCAN TO FOLLOW")
    im.paste(card, ((W - card.width) // 2, 860), card if card.mode == "RGBA" else None)
    for txt, y in ((follow, 1340), ("TURN NEGATIVE INTO POSITIVE", 1410),
                   ("FROM THE SCREENPLAY BY ELVIN TORRES SR.", 1640)):
        f = mid if y == 1340 else sm
        tw = d.textlength(txt, font=f)
        d.text(((W - tw) / 2, y), txt, font=f, fill=(230, 230, 236) if y != 1640 else (141, 140, 156))
    im.save(path)


# ---------------------------------------------------------------- ffmpeg
def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(" ".join(cmd[:6]) + " ... " + r.stderr[-800:])
    return r.stdout


def probe_dur(p):
    try:
        return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).strip())
    except Exception:  # noqa: BLE001
        return 0.0


def has_audio(p):
    return "audio" in sh(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", p])


def wav_dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def render_shot(src, out, dur, grade, ovs, still=False):
    """One graded 1080x1920 shot with its audio (or silence); ovs = [(png, start, end)] burned in."""
    vin = (["-loop", "1", "-t", f"{dur:.3f}", "-i", src] if still else ["-i", src])
    zoom = ("zoompan=z='min(1.0+0.0009*on,1.12)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            if still else "")
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration=3,trim=0:{dur:.3f},setpts=PTS-STARTPTS,{GRADE[grade]},"
          f"noise=alls=7:allf=t,vignette=PI/4.5,format=yuv420p[v0]")
    ov_in = []
    for k, (png, a, b) in enumerate(ovs, 1):
        ov_in += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        vf += (f";[{k}:v]format=rgba,fade=t=in:st={a + 0.1:.3f}:d=0.25:alpha=1,"
               f"fade=t=out:st={max(a + 0.4, b - 0.3):.3f}:d=0.25:alpha=1[o{k}];[v{k-1}][o{k}]overlay=0:0[v{k}]")
    vf += f";[v{len(ovs)}]format=yuv420p[vo]"
    aud = (not still) and has_audio(src)
    if aud:
        af = f";[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{dur:.3f},afade=t=in:d=0.08,afade=t=out:st={max(0, dur-0.15):.3f}:d=0.15[a]"
    else:
        af = f";anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[a]"
    sh(["ffmpeg", "-y", "-v", "error", *vin, *ov_in,
        "-filter_complex", vf + af, "-map", "[vo]", "-map", "[a]", "-r", str(FPS), "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{dur:.3f}", out])


def card_clip(png, out, dur):
    sh(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", f"{dur}", "-i", png, "-f", "lavfi", "-i",
        "anullsrc=r=48000:cl=stereo", "-filter_complex",
        f"[0:v]scale={W}:{H},zoompan=z='1.0+0.0006*on':d=1:s={W}x{H}:fps={FPS},noise=alls=6:allf=t,"
        f"fade=t=in:d=0.4,fade=t=out:st={dur-0.4}:d=0.4,format=yuv420p[v]", "-map", "[v]", "-map", "1:a",
        "-t", f"{dur}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-ar", "48000", out])


# ---------------------------------------------------------------- episode
def build(series, n, out, work):
    sdir = os.path.join(ROOT, "content", "movie", series)
    cast = json.load(open(os.path.join(sdir, "cast.json")))
    ep = next(e for e in json.load(open(os.path.join(sdir, "episodes.json")))["episodes"] if e["n"] == n)
    work = os.path.join(work, f"{series}-ep{n:02d}")
    os.makedirs(work, exist_ok=True)
    report = {"series": series, "episode": n, "title": ep["title"], "balance_start": balance(), "shots": []}
    log(f"EPISODE {n}: {ep['title']}  balance:", report["balance_start"])

    ids = sorted({c for s in ep["shots"] for c in s.get("c", [])})
    refs = cast_refs(sdir, cast, ids, work)
    vo = narrate([s["s"] for s in ep["shots"] if s["t"] == "vo"], work)

    # timing: vo shots must hold the whole narration line
    for s in ep["shots"]:
        if s["t"] == "vo":
            s["d"] = min(10, max(s["d"], math.ceil(wav_dur(vo[s["s"]]) + 0.9)))

    def one(i_s):
        i, s = i_s
        seed = int(_h(series, n, i), 16) % 2_000_000_000
        rec = {"i": i, "t": s["t"], "v": s["v"][:80]}
        try:
            fpath, furl = make_frame(s, cast, refs, work, seed)
            rec["frame"] = furl
            clip, model, errs = make_clip(s, cast, furl, work, seed, s["d"])
            rec.update(model=model or "still", errors=errs)
            return i, fpath, clip, rec
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)[:300]
            return i, None, None, rec

    with cf.ThreadPoolExecutor(max_workers=int(os.environ.get("IRUN_MOVIE_PARALLEL", "4"))) as ex:
        results = sorted(ex.map(one, enumerate(ep["shots"])), key=lambda r: r[0])

    parts, vo_at, t = [], [], 0.0
    for i, fpath, clip, rec in results:
        s = ep["shots"][i]
        report["shots"].append(rec)
        if not fpath:
            log("shot", i, "FAILED", rec.get("error"))
            continue
        dur = float(s["d"])
        if clip and s["t"] == "talk":
            dur = max(dur, min(probe_dur(clip), 8.0))  # never cut a spoken line short
        ovs = []
        if s.get("loc"):
            ovs.append((os.path.join(work, f"loc_{i}.png"), 0.0, min(dur, 3.2)))
            overlay_png(ovs[-1][0], loc=s["loc"])
        if s["t"] == "talk":  # each speaker's line on screen for its share of the shot
            lines = [ln for _, ln in speakers(s["s"], cast)]
            total_chars = sum(len(x) for x in lines) or 1
            a = 0.2
            span = dur - 0.5
            for k, ln in enumerate(lines):
                b = a + span * len(ln) / total_chars
                ovs.append((os.path.join(work, f"sub_{i}_{k}.png"), a, b))
                overlay_png(ovs[-1][0], sub=ln)
                a = b
        p = os.path.join(work, f"shot_{i:02d}.mp4")
        render_shot(clip or fpath, p, dur, s["g"], ovs, still=clip is None)
        if s["t"] == "vo":
            vo_at.append((t + 0.35, vo[s["s"]]))
        parts.append(p)
        t += dur
        if i == 0:  # title card after the cold open
            tpng = os.path.join(work, "title.png")
            title_card(tpng, cast, ep)
            tp = os.path.join(work, "title.mp4")
            card_clip(tpng, tp, 2.8)
            parts.append(tp)
            title_at = t
            t += 2.8
    acct = json.load(open(os.path.join(ROOT, "config", "series.json")))
    ser = next((x for x in acct["series"] if x["id"] == series), {})
    epng = os.path.join(work, "end.png")
    end_card(epng, cast, ep, "FOLLOW @HOODSTAR365", ser.get("link", "https://www.instagram.com/hoodstar365/"))
    ep_end = os.path.join(work, "end.mp4")
    card_clip(epng, ep_end, 4.5)
    parts.append(ep_end)
    total = t + 4.5

    lst = os.path.join(work, "concat.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    cut = os.path.join(work, "cut.mp4")
    sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", cut])

    score = make_score(ep, total, work)
    # mix: dialogue/ambience from the clips + narrator + score ducked under both
    ins = ["-i", cut, "-i", score] + sum((["-i", f] for _, f in vo_at), [])
    fc = [f"[0:a]volume=1.0[dlg]",
          f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.2f},"
          f"afade=t=in:d=1.5,afade=t=out:st={total-2.5:.2f}:d=2.5,volume=0.55[sc]"]
    names = []
    for k, (at, _) in enumerate(vo_at):
        fc.append(f"[{k+2}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(at*1000)}|{int(at*1000)},"
                  f"volume=1.35[n{k}]")
        names.append(f"[n{k}]")
    if names:
        fc.append("".join(names) + f"amix=inputs={len(names)}:normalize=0[nar]")
        fc.append("[dlg][nar]amix=inputs=2:normalize=0,asplit=2[voice][key]")
    else:
        fc.append("[dlg]asplit=2[voice][key]")
    fc.append("[sc][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
    fc.append(f"[voice][duck]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5,atrim=0:{total:.2f}[mix]")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sh(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[mix]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    poster = out.rsplit(".", 1)[0] + ".jpg"
    sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{min(1.5, total/2):.2f}", "-i", out, "-frames:v", "1", "-q:v", "3",
        poster])
    report.update(duration=round(probe_dur(out), 2), balance_end=balance(),
                  stills=[r["i"] for r in report["shots"] if r.get("model") == "still"],
                  failed=[r["i"] for r in report["shots"] if r.get("error")])
    json.dump(report, open(out.rsplit(".", 1)[0] + ".json", "w"), indent=2)
    log("done", out, report["duration"], "s  stills:", report["stills"], "failed:", report["failed"])
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("episode", nargs="?", type=int)
    ap.add_argument("out", nargs="?")
    ap.add_argument("--work", default=os.path.join(ROOT, "work"))
    ap.add_argument("--refs-only", action="store_true", help="generate the cast reference portraits and stop")
    a = ap.parse_args()
    if a.refs_only:
        sd = os.path.join(ROOT, "content", "movie", a.series)
        print(json.dumps(cast_refs(sd, json.load(open(os.path.join(sd, "cast.json"))), None, a.work), indent=2))
    else:
        build(a.series, a.episode, a.out, a.work)
