"""iRun Video: one photo + one song + a description -> a music video or a short film starring that person.

Music video
  1. song     find the strongest section for the chosen length, estimate the tempo, cut points on the bar
  2. plan     Claude writes a shot list from the description (performance shots + story shots); offline fallback
  3. frames   identity-locked stills: the member's photo is the face reference for every shot
  4. motion   performance shots are audio-driven (the song slice is the reference audio, so the lips follow the
              vocal); story shots are image-to-video b-roll
  5. cut      graded 1080x1920 shots on the bar, artist/title super, end card with a QR to HSW365studio signup;
              the original song is the soundtrack, untouched
Short film
  Same casting. Claude writes scenes with spoken lines (dialogue model, lip-synced), narration (Kokoro, free) and
  b-roll; the member's song is the score, ducked under dialogue and narration. Title card + end card.

All generation goes through Pollinations (POLLINATIONS_TOKEN), reusing engine/movie.py's job/cache helpers.

  python engine/musicvideo.py photo.jpg song.mp3 out.mp4 --kind music_video --desc "..." [--style neon]
         [--length 60] [--title "No Lane"] [--artist "Hoodstar365"] [--work work/]
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movie as M  # noqa: E402

W, H, FPS = M.W, M.H, M.FPS
LIPSYNC_MODELS = [m for m in os.environ.get("IRUN_VIDEO_LIPSYNC_MODELS",
                  "bytedance/seedance-2.0,alibaba/wan-3.0,minimax/minimax-h3-max-turbo").split(",") if m]
BROLL_MODEL = os.environ.get("IRUN_VIDEO_BROLL_MODEL", M.BROLL_MODEL)
SIGNUP = os.environ.get("IRUN_VIDEO_SIGNUP", "https://hsw365.github.io/STUDIO365/?signup")

# Look, grade and accent colour per style the member can pick.
STYLES = {
    "cinematic": ("Prestige film look: anamorphic lens, shallow depth of field, motivated practical lighting, rich"
                  " shadows, 35mm film texture", "street", (34, 211, 238)),
    "street": ("Gritty urban music video: night city streets, wet asphalt, sodium street lights, handheld energy,"
               " real locations", "street", (214, 32, 39)),
    "neon": ("Neon-lit night: magenta and cyan neon signs, haze, reflections on glass and chrome, glossy and moody",
             "neon", (236, 72, 153)),
    "luxury": ("Luxury editorial: penthouse, gold accents, marble, designer wardrobe, warm key light, magazine polish",
               "gold", (234, 179, 8)),
    "dark": ("Dark and dramatic: hard top light, deep blacks, smoke, silhouettes, rain, intense close-ups",
             "dark", (148, 163, 184)),
    "dreamy": ("Dreamy and soft: golden hour, lens flares, slow motion, pastel sky, floating fabric, soft focus",
               "healing", (251, 191, 36)),
    "vintage": ("Vintage 90s music video: VHS-era colour, fisheye moments, film grain, retro wardrobe and cars",
                "vintage", (249, 115, 22)),
    "anime": ("Stylised anime-inspired cinematography: bold colour, dramatic wind, speed lines feel, vivid skies,"
              " still photoreal people", "anime", (129, 140, 248)),
    "performance": ("Stage performance: concert lights, smoke, crowd silhouettes, spotlights, big LED wall",
                    "neon", (34, 211, 238)),
}
M.GRADE.update({
    "neon": "eq=contrast=1.15:saturation=1.25:brightness=-0.02,colorbalance=bs=0.12:rh=0.08:rm=0.04",
    "gold": "eq=contrast=1.1:saturation=1.05,colorbalance=rm=0.08:gm=0.03:bm=-0.08:rh=0.06",
    "dark": "eq=contrast=1.2:saturation=0.7:brightness=-0.05,colorbalance=bs=0.05",
    "vintage": "eq=contrast=1.05:saturation=0.75,colorbalance=rm=0.07:gm=0.04:bm=-0.04,curves=preset=vintage",
    "anime": "eq=contrast=1.05:saturation=1.2:brightness=0.02",
})


def log(*a):
    print("[video]", *a, flush=True)


# ---------------------------------------------------------------- song
def decode(path, sr=22050):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32), sr


def analyse(path, length):
    """(start, length, bpm) for the strongest section of the song that is `length` seconds long."""
    x, sr = decode(path)
    total = len(x) / sr
    if total < 8:
        raise RuntimeError("That song is too short. Upload at least 8 seconds of audio.")
    length = min(float(length), total)
    hop = 512
    n = len(x) // hop
    fr = x[: n * hop].reshape(n, hop)
    e = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    # tempo: autocorrelation of the onset envelope between 70 and 180 bpm
    on = np.maximum(0, np.diff(np.log(e + 1e-4)))
    on = on - on.mean()
    ac = np.correlate(on, on, mode="full")[len(on) - 1:]
    fps = sr / hop
    lags = np.arange(int(fps * 60 / 180), int(fps * 60 / 70) + 1)
    lags = lags[lags < len(ac)]
    bpm = 92.0
    if len(lags):
        lag = lags[int(np.argmax(ac[lags]))]
        bpm = float(60 * fps / lag)
        while bpm < 80:
            bpm *= 2
        while bpm > 160:
            bpm /= 2
    # section: highest mean loudness over the window (1 s resolution), never the first or last 2 seconds if avoidable
    nsec = int(len(e) / fps)
    sec = np.array([e[int(k * fps):int((k + 1) * fps)].mean() for k in range(nsec)]) if nsec else e
    win = max(1, int(round(length)))
    if len(sec) <= win:
        start = 0.0
    else:
        cs = np.concatenate([[0], np.cumsum(sec)])
        means = (cs[win:] - cs[:-win]) / win
        start = float(np.argmax(means))
    start = max(0.0, min(start, total - length))
    beat = 60.0 / bpm
    start = round(start / beat) * beat if start > beat else start  # land on a beat
    start = max(0.0, min(start, total - length))
    return start, length, bpm, total


def cut_points(length, bpm, kind):
    """Shot durations that land on the bar and sum to length."""
    bar = 4 * 60.0 / bpm
    unit = bar if bar >= 1.8 else bar * 2
    lo, hi = (2.4, 5.6) if kind == "music_video" else ((2.0, 4.5) if kind == "ugc" else (3.0, 7.0))
    pattern = [2, 1, 1, 2, 1, 2, 2, 1] if unit < 3 else [1, 1, 2, 1, 1, 1, 2, 1]
    out, t, i = [], 0.0, 0
    while t < length - 0.5:
        d = unit * pattern[i % len(pattern)]
        while d > hi and d - unit >= lo:
            d -= unit
        while d < lo:
            d += unit
        d = min(d, length - t)
        out.append(round(d, 3))
        t += d
        i += 1
    if len(out) > 1 and out[-1] < 1.5:
        out[-2] = round(out[-2] + out.pop(), 3)
    return out


# ---------------------------------------------------------------- plan
def plan(kind, desc, style, title, artist, durs):
    look = STYLES[style][0]
    n = len(durs)
    if kind == "ugc":
        sysmsg = ("You are a top UGC ad creative director (TikTok/Reels creator ads that convert). You write shot"
                  " lists for a vertical 9:16 AI-filmed creator video starring one person (the STAR, shown in a"
                  " reference photo) talking to their phone camera. Return JSON only.")
        user = (f"What they are promoting / saying:\n{desc}\n\nWrite exactly {n} shots, in order, with these lengths"
                f" in seconds: {durs}.\nEach shot: {{\"type\": \"talk\" | \"story\", \"v\": \"one sentence: setting,"
                " framing, action\", \"line\": \"what the STAR says (talk only, max 14 words, casual, first person)\"}}."
                " talk = the STAR holds the phone selfie-style or it sits on a tripod, talking straight to the lens,"
                " authentic, real home/car/street setting. story = B-roll: hands-on product or proof shots, POV, the"
                " result, no talking. Shot 1 is a scroll-stopping hook line in the first 2 seconds. Structure: hook,"
                " problem, discovery, proof, call to action as the last talk line. About 60% talk. No on-screen text"
                " in the picture.\nReturn {\"look\": \"one sentence: wardrobe, setting, vibe\", \"shots\": [...]}.")
    elif kind == "music_video":
        sysmsg = ("You are a top music video director. You write shot lists for a vertical 9:16 AI-filmed music"
                  " video starring one artist (the STAR, shown in a reference photo). Return JSON only.")
        user = (f"Song: {title or 'untitled'} by {artist or 'the artist'}.\nThe artist's idea for the video:\n{desc}\n\n"
                f"Visual style: {look}.\nWrite exactly {n} shots, in order, with these lengths in seconds: {durs}.\n"
                "Each shot: {\"type\": \"perform\" | \"story\", \"v\": \"one vivid sentence: location, action, camera"
                " move, lighting, wardrobe\"}. perform = the STAR sings straight to camera or performs in a strong"
                " location (lips must be visible, face clear). story = cinematic b-roll that tells the idea (the STAR"
                " may appear, other people may appear, no singing). About half perform, start with a striking"
                " visual, build energy, end on the strongest image. Keep the STAR's wardrobe consistent unless the"
                " idea says otherwise. Never put words, logos or captions in the picture.\n"
                "Return {\"look\": \"one sentence: wardrobe, palette, recurring motif\", \"shots\": [...]}.")
    else:
        sysmsg = ("You are an award-winning short film director. You write shot lists for a vertical 9:16 AI-filmed"
                  " short film starring one person (the STAR, shown in a reference photo). Return JSON only.")
        user = (f"Their song plays as the score{f' ({title})' if title else ''}.\nThe story they want:\n{desc}\n\n"
                f"Visual style: {look}.\nWrite exactly {n} shots, in order, with these lengths in seconds: {durs}.\n"
                "Each shot: {\"type\": \"talk\" | \"story\" | \"vo\", \"v\": \"one vivid sentence: location, action,"
                " camera, lighting\", \"who\": \"star\" or a short description of the other character speaking"
                " (talk only), \"line\": \"what is said\"}. talk = an on-camera spoken line (max 14 words, face"
                " visible). vo = the STAR's inner narration over b-roll (max 18 words). story = no words. Use 3-6 talk"
                " shots, 2-4 vo shots, the rest story. Clear beginning, turn, and ending. No on-screen text.\n"
                "Return {\"film\": \"short title, 1-4 words\", \"look\": \"one sentence: wardrobe, palette, motif\","
                " \"shots\": [...]}.")
    try:
        import llm
        if not llm.available():
            raise RuntimeError("no ANTHROPIC_API_KEY")
        p = llm.ask_json(sysmsg, user, max_tokens=5000)
        shots = p.get("shots") or []
        if len(shots) < n:
            raise ValueError(f"plan has {len(shots)} shots, need {n}")
        p["shots"] = shots[:n]
        return p
    except Exception as e:  # noqa: BLE001
        log("plan fallback:", e)
        return fallback_plan(kind, desc, n, title)


def brief_plan(brief, durs):
    """A director's brief: chapters (each a place/act) with perform and story shot pools, split over the song
    by weight. Every chapter opens on a location super. Keeps the order the artist asked for."""
    ch = brief["chapters"]
    n = len(durs)
    wsum = sum(c.get("weight", 1) for c in ch)
    counts = [max(2, round(n * c.get("weight", 1) / wsum)) for c in ch]
    while sum(counts) > n:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < n:
        counts[counts.index(max(counts))] += 1
    shots = []
    for c, k in zip(ch, counts):
        perf, story = c.get("perform") or [], c.get("story") or []
        pi = si = 0
        for j in range(k):
            use_perf = perf and (not story or j % 2 == (0 if c.get("open") == "perform" else 1))
            if use_perf:
                shots.append({"type": "perform", "v": perf[pi % len(perf)]}); pi += 1
            else:
                shots.append({"type": "story", "v": story[si % len(story)]}); si += 1
            shots[-1]["fx"] = c.get("fx", "")
            if j == 0 and c.get("loc"):
                shots[-1]["loc"] = c["loc"]
    return {"look": brief.get("look", ""), "shots": shots[:n]}


def fallback_plan(kind, desc, n, title):
    idea = desc.strip().rstrip(".")
    perf = ["the STAR sings straight into the lens, slow push-in, close-up",
            "the STAR performs in a wide shot, camera orbits slowly around them",
            "the STAR sings with intensity, low angle, light flaring behind them",
            "the STAR performs centre frame, crowd silhouettes behind, smoke in the light"]
    story = [f"cinematic b-roll that shows: {idea}", f"the STAR walking through the world of: {idea}",
             f"a detail shot that captures the feeling of: {idea}", f"a wide establishing shot for: {idea}"]
    shots = []
    for i in range(n):
        if kind == "music_video":
            shots.append({"type": "perform" if i % 2 == 0 else "story",
                          "v": (perf if i % 2 == 0 else story)[(i // 2) % 4]})
        else:
            t = "vo" if i in (1, n // 2) else ("story" if i % 3 else "talk")
            shots.append({"type": t, "v": story[i % 4], "who": "star",
                          "line": "I made it out. Now watch me." if t != "story" else ""})
    return {"film": (title or "MY STORY")[:24], "look": "consistent wardrobe, high contrast", "shots": shots}


# ---------------------------------------------------------------- generation
STAR = ("The STAR is the exact person in the reference photo: same face, same skin tone, same facial hair, same"
        " hairstyle, same age and build. Keep their identity exactly. Use only the person from the reference photo, never its background: place them fully inside the new scene with matching light.")


UGC_LOOK = ("Authentic creator video shot on an iPhone front camera: natural window light, real lived-in setting,"
            " slight handheld wobble, true-to-life colour, not cinematic, not glossy")


def frame_for(shot, look_style, look, photo_url, work, seed):
    v = shot["v"].replace("the STAR", "the person from the reference photo").replace("STAR", "the person")
    p = (f"Cinematic vertical film still, {look_style}. {v}. {look}. {STAR} Photorealistic, real people, no text,"
         f" no captions, no watermark, no logos.")
    out = os.path.join(work, f"frame_{M._h(p, M.IMAGE_MODEL, seed)}.jpg")
    params = {"model": M.IMAGE_MODEL, "width": 1080, "height": 1920, "aspectRatio": "9:16", "seed": seed,
              "image": photo_url}
    try:
        u = M.media_job("image", p, params, out)
    except Exception as e:  # noqa: BLE001
        log("frame retry:", str(e)[:200])
        params["seed"] = seed + 1
        u = M.media_job("image", p, params, out + ".2.jpg")
        out = out + ".2.jpg"
    return out, (u or M.public_url(out))


def slice_song(song, t0, dur, work):
    out = os.path.join(work, f"slice_{t0:.2f}_{dur:.2f}.mp3")
    if not os.path.exists(out):
        M.sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", song, "-ac", "2",
              "-ar", "44100", "-b:a", "192k", out])
    return M.public_url(out)


def clip_for(shot, look_style, frame_url, work, seed, dur, audio_url=None):
    v = shot["v"].replace("the STAR", "the person").replace("STAR", "the person")
    kind = shot["type"]
    if kind == "perform":
        prompt = (f"{v}. The person sings the song in the reference audio, lips moving in perfect sync with every"
                  f" word of the vocal, natural breathing and expression, music video performance. {look_style}."
                  " Keep the face identical to the first frame. No text on screen.")
        models = LIPSYNC_MODELS + [BROLL_MODEL] + M.FALLBACK_VIDEO
    elif kind == "talk":
        who = shot.get("who") or "star"
        speaker = "The person" if who.lower() in ("star", "the star") else f"The {who}"
        prompt = (f"{v}. {speaker} says, clearly and naturally: \"{shot.get('line', '')}\" Lips move in sync with the"
                  f" words. Realistic ambient sound, no music, no subtitles. {look_style}.")
        models = [M.TALK_MODEL] + M.FALLBACK_VIDEO
    else:
        prompt = (f"{v}. Realistic cinematic movement, natural motion, subtle camera move. {look_style}."
                  " No one talking, no text on screen.")
        models = [BROLL_MODEL] + M.FALLBACK_VIDEO
    errs = []
    for m in models:
        d = int(math.ceil(dur))
        if m in LIPSYNC_MODELS:
            d = 5 if m == "alibaba/wan-3.0" else max(4 if m.startswith("bytedance") else 5, min(15, d))
            if m.startswith("minimax"):
                d = 5 if d <= 5 else (10 if d <= 10 else 15)
        elif m == M.TALK_MODEL:
            d = next((x for x in M.TALK_DURS if x >= dur), M.TALK_DURS[-1])
        else:
            d = max(2, min(10, d))
        params = {"model": m, "image": frame_url, "duration": d, "aspectRatio": "9:16", "resolution": "720p",
                  "seed": seed}
        if kind == "perform" and m in LIPSYNC_MODELS and audio_url:
            params["reference_audios"] = audio_url
            params["audio"] = "true"
        if kind == "talk":
            params["audio"] = "true"
        out = os.path.join(work, f"clip_{M._h(prompt, params)}.mp4")
        try:
            M.media_job("video", prompt, params, out)
            if M.probe_dur(out) < 1.0:
                raise RuntimeError("empty clip")
            return out, m, errs
        except Exception as e:  # noqa: BLE001
            errs.append(f"{m}: {str(e)[:200]}")
            log("clip fallback", m, str(e)[:160])
    return None, None, errs


# ---------------------------------------------------------------- production effects
def fx(path, i, shot, dur, accent, chapter_open=False):
    """Big-budget finish on one rendered shot, in place: bloom/halation on the highlights, a hit flash on the
    cut (white on chapter opens, accent colour on others), chromatic split on impact shots, a speed-ramp punch-in
    on performance shots, and drifting light leaks. Every effect lands on the cut, so it hits on the bar."""
    r, g, b = accent
    hexc = f"0x{r:02x}{g:02x}{b:02x}"
    flash_col = "white" if chapter_open else hexc
    chain = ["split[a][b]", "[b]gblur=sigma=28,eq=brightness=0.06:saturation=1.3[bl]",
             "[a][bl]blend=all_mode=screen:all_opacity=0.32"]
    if shot.get("type") == "perform":  # slow push-in that kicks on the downbeat
        chain.append(f"zoompan=z='if(lt(on,4),1.07-0.0175*on,1.0+0.0007*(on-4))':d=1:x='iw/2-(iw/zoom/2)':"
                     f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
    if "split" in shot.get("fx", "") or i % 5 == 3:
        chain.append("rgbashift=rh=-6:bh=6:enable='lt(t,0.35)'")
    if "leak" in shot.get("fx", "") or i % 3 == 1:  # warm light leak sweeping across
        chain.append(f"drawbox=x='-{W}+{W*2}*t/{max(dur, 1):.2f}':y=0:w={W//2}:h={H}:color=0xffb070@0.10:t=fill")
    chain.append(f"fade=t=in:st=0:d={0.18 if chapter_open else 0.1}:color={flash_col}")
    if i % 2 == 0:
        chain.append("eq=contrast=1.04")
    vf = ",".join(chain[3:])
    full = f"[0:v]{chain[0]};{chain[1]};{chain[2]}" + (f",{vf}" if vf else "") + ",format=yuv420p[v]"
    tmp = path + ".fx.mp4"
    M.sh(["ffmpeg", "-y", "-v", "error", "-i", path, "-filter_complex", full, "-map", "[v]", "-map", "0:a?",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", "-t", f"{dur:.3f}", tmp])
    os.replace(tmp, path)


def loc_png(path, text, accent):
    """Chapter super: huge outlined place name with a thin accent rule (top-left, trailer style)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _fit(d, text.upper(), "BarlowCondensed-ExtraBold.ttf", 170, W - 140)
    d.text((70, 210), text.upper(), font=f, fill=(255, 255, 255, 0), stroke_width=4, stroke_fill=(255, 255, 255, 235))
    d.rectangle((74, 222 + f.size, 74 + 140, 228 + f.size), fill=accent + (255,))
    im.save(path)


# ---------------------------------------------------------------- cards
def _center(d, y, txt, font, fill, stroke=0, sfill=None):
    tw = d.textlength(txt, font=font)
    d.text(((W - tw) / 2, y), txt, font=font, fill=fill, stroke_width=stroke, stroke_fill=sfill)


def _fit(d, txt, name, start, maxw):
    s = start
    f = M.F(name, s)
    while d.textlength(txt, font=f) > maxw and s > 40:
        s -= 6
        f = M.F(name, s)
    return f


def super_png(path, artist, title, accent):
    """Artist / title super for the opening shot (bottom-left, music video convention)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = H - 520
    if artist:
        f = _fit(d, artist.upper(), "BarlowCondensed-ExtraBold.ttf", 118, W - 150)
        d.text((72, y), artist.upper(), font=f, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 170))
        y += f.size + 6
    if title:
        f = _fit(d, f"“{title.upper()}”", "BarlowCondensed-SemiBold.ttf", 64, W - 150)
        d.text((76, y), f"“{title.upper()}”", font=f, fill=accent + (255,), stroke_width=2,
               stroke_fill=(0, 0, 0, 170))
        y += f.size + 18
    d.rectangle((76, y, 76 + 120, y + 6), fill=accent + (255,))
    im.save(path)


def title_png(path, film, poster, accent):
    bg = Image.open(poster).convert("RGB")
    bg = ImageOps.fit(bg, (W, H)).filter(ImageFilter.GaussianBlur(18))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (4, 4, 8)), 0.72)
    d = ImageDraw.Draw(bg)
    words = film.upper().split() or ["UNTITLED"]
    y = 820 - (len(words) - 1) * 95
    for w in words:
        f = _fit(d, w, "BarlowCondensed-ExtraBold.ttf", 210, W - 140)
        _center(d, y, w, f, (246, 246, 250), 3, accent)
        y += 190
    _center(d, y + 20, "A SHORT FILM", M.F("SpaceMono-Bold.ttf", 34), (215, 215, 225))
    bg.save(path)


def end_png(path, artist, title, accent, kind, poster=None):
    import qr
    if poster and os.path.exists(poster):
        im = ImageOps.fit(Image.open(poster).convert("RGB"), (W, H)).filter(ImageFilter.GaussianBlur(26))
        im = Image.blend(im, Image.new("RGB", (W, H), (4, 4, 8)), 0.8)
    else:
        im = Image.new("RGB", (W, H), (5, 5, 9))
    d = ImageDraw.Draw(im)
    y = 300
    if artist:
        f = _fit(d, artist.upper(), "BarlowCondensed-ExtraBold.ttf", 150, W - 140)
        _center(d, y, artist.upper(), f, (246, 246, 250), 2, accent)
        y += f.size + 10
    if title:
        f = _fit(d, title.upper(), "BarlowCondensed-SemiBold.ttf", 76, W - 140)
        _center(d, y, title.upper(), f, accent)
        y += f.size
    card = qr.card(SIGNUP, size=420, label="MAKE YOURS")
    im.paste(card, ((W - card.width) // 2, max(y + 120, 720)), card)
    y = max(y + 120, 720) + card.height + 70
    mid = M.F("BarlowCondensed-SemiBold.ttf", 58)
    sm = M.F("SpaceMono-Bold.ttf", 30)
    what = {"music_video": "YOUR SONG. YOUR FACE. YOUR VIDEO.", "ugc": "YOUR PRODUCT. YOUR FACE. YOUR AD."}.get(
        kind, "YOUR STORY. YOUR FACE. YOUR FILM.")
    _center(d, y, what, mid, (240, 240, 246))
    _center(d, y + 80, "MADE WITH HSW365STUDIO  ·  POWERED BY iRUN", sm, (150, 150, 165))
    im.save(path)


# ---------------------------------------------------------------- build
def build(photo, song, out, kind="music_video", desc="", style="cinematic", length=60, title="", artist="",
          work="work", progress=None, brief=None):
    style = style if style in STYLES else "cinematic"
    look_style, grade, accent = STYLES[style]
    os.makedirs(work, exist_ok=True)
    step = progress or (lambda p, s: log(f"{p:3d}%", s))
    report = {"kind": kind, "style": style, "balance_start": M.balance(), "shots": []}

    step(4, "Listening to your song")
    if kind == "ugc":
        look_style, grade = UGC_LOOK, "home"
    if song:
        t0, length, bpm, total = analyse(song, length)
    else:
        t0, bpm, total = 0.0, 120.0, float(length)
    durs = cut_points(length, bpm, kind)
    report.update(song_start=round(t0, 2), length=round(length, 2), bpm=round(bpm, 1), song_seconds=round(total, 1))
    log(f"section {t0:.1f}s +{length:.1f}s  bpm {bpm:.1f}  shots {len(durs)}")

    step(8, "Writing your shot list")
    pl = brief_plan(brief, durs) if brief else plan(kind, desc, style, title, artist, durs)
    look = pl.get("look", "")
    report["plan"] = pl

    step(12, "Casting you")
    pimg = Image.open(photo)
    pimg = ImageOps.exif_transpose(pimg).convert("RGB")
    if brief and brief.get("mirror_photo"):  # selfie-camera photo: un-mirror so printed text on clothes reads right
        pimg = ImageOps.mirror(pimg)
    pimg.thumbnail((1536, 1536))
    ref = os.path.join(work, "star.jpg")
    pimg.save(ref, quality=93)
    photo_url = M.public_url(ref)

    starts = np.concatenate([[0.0], np.cumsum(durs)[:-1]])
    done = [0]

    def one(i):
        s = pl["shots"][i]
        s["type"] = s.get("type") if s.get("type") in ("perform", "story", "talk", "vo") else "story"
        if kind == "music_video" and s["type"] in ("talk", "vo"):
            s["type"] = "perform"
        seed = int(M._h(photo_url, desc, i), 16) % 2_000_000_000
        rec = {"i": i, "type": s["type"], "v": s.get("v", "")[:90]}
        try:
            fpath, furl = frame_for(s, look_style, look, photo_url, work, seed)
            rec["frame"] = furl
            aurl = None
            if s["type"] == "perform":
                need = max(4.0, durs[i])
                aurl = slice_song(song, t0 + starts[i], min(need, total - (t0 + starts[i])), work)
            clip, model, errs = clip_for(s, look_style, furl, work, seed, durs[i], aurl)
            rec.update(model=model or "still", errors=errs)
            res = (i, fpath, clip, rec)
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)[:300]
            res = (i, None, None, rec)
        done[0] += 1
        step(14 + int(66 * done[0] / len(durs)), f"Filming shot {done[0]} of {len(durs)}")
        return res

    step(14, f"Filming shot 1 of {len(durs)}")
    with cf.ThreadPoolExecutor(max_workers=int(os.environ.get("IRUN_MOVIE_PARALLEL", "4"))) as ex:
        results = sorted(ex.map(one, range(len(durs))), key=lambda r: r[0])

    good = [r for r in results if r[1]]
    if len(good) < max(2, len(durs) // 2):
        raise RuntimeError("Too many shots failed to render. Nothing was charged to your plan; try again.")

    step(82, "Cutting it on the beat")
    vo_lines = [pl["shots"][i].get("line", "") for i, f, c, r in results
                if f and kind == "short_film" and pl["shots"][i]["type"] == "vo" and pl["shots"][i].get("line")]
    vo = M.narrate(vo_lines, work) if vo_lines else {}
    parts, vo_at, t, last_frame = [], [], 0.0, ref
    for i, fpath, clip, rec in results:
        report["shots"].append(rec)
        s = pl["shots"][i]
        dur = durs[i]
        if not fpath:  # keep the cut on the music: hold the previous frame instead of dropping time
            fpath, clip = last_frame, None
        last_frame = fpath
        ovs = []
        if s.get("loc"):
            ovs.append((os.path.join(work, f"loc_{i}.png"), 0.15, min(dur, 3.0)))
            loc_png(ovs[-1][0], s["loc"], accent)
        if i == 0 and kind == "music_video" and (artist or title):
            ovs.append((os.path.join(work, "super.png"), 0.4, min(dur, 3.6)))
            super_png(ovs[-1][0], artist, title, accent)
        if kind in ("short_film", "ugc") and s["type"] == "talk" and s.get("line"):
            ovs.append((os.path.join(work, f"sub_{i}.png"), 0.2, dur - 0.2))
            M.overlay_png(ovs[-1][0], sub=s["line"])
        if kind == "short_film" and s["type"] == "vo" and s.get("line") in vo:
            dur = max(dur, min(9.0, M.wav_dur(vo[s["line"]]) + 0.8))
            vo_at.append((t + 0.3, vo[s["line"]]))
        if kind in ("short_film", "ugc") and clip and s["type"] == "talk":
            dur = max(dur, min(M.probe_dur(clip), 8.0))
        p = os.path.join(work, f"shot_{i:02d}.mp4")
        M.render_shot(clip or fpath, p, dur, grade, ovs, still=clip is None)
        if kind == "music_video":
            fx(p, i, s, dur, accent, chapter_open=bool(s.get("loc")) or i == 0)
        parts.append(p)
        t += dur
        if i == 0 and kind == "short_film":
            tpng = os.path.join(work, "title.png")
            title_png(tpng, pl.get("film") or title or "UNTITLED", fpath, accent)
            tp = os.path.join(work, "title.mp4")
            M.card_clip(tpng, tp, 2.8)
            parts.append(tp)
            t += 2.8
    body = t
    poster_src = next((r[1] for r in results if r[1]), None)
    epng = os.path.join(work, "end.png")
    end_png(epng, artist, title if kind == "music_video" else (pl.get("film") or title), accent, kind, poster_src)
    ep = os.path.join(work, "end.mp4")
    end_len = 4.0
    M.card_clip(epng, ep, end_len)
    parts.append(ep)
    total_len = body + end_len

    lst = os.path.join(work, "concat.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    cut = os.path.join(work, "cut.mp4")
    M.sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", cut])

    step(90, "Mixing the sound")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if kind == "music_video":
        # the member's song is the soundtrack: exact section, fade out over the end card
        tail = min(end_len, max(0.0, total - (t0 + body)))
        a_len = body + tail
        fc = (f"[1:a]atrim=0:{a_len:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
              f"afade=t=in:d=0.25,afade=t=out:st={max(0, a_len - 2.5):.3f}:d=2.5,apad,atrim=0:{total_len:.3f},"
              f"loudnorm=I=-14:TP=-1.0[mix]")
        M.sh(["ffmpeg", "-y", "-v", "error", "-i", cut, "-ss", f"{t0:.3f}", "-i", song, "-filter_complex", fc,
              "-map", "0:v", "-map", "[mix]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags",
              "+faststart", "-t", f"{total_len:.3f}", out])
    else:
        # dialogue from the clips + narration, with the member's song as the score ducked under both
        if not song:  # UGC without a song: a near-silent room-tone bed so the mix graph stays the same
            song = os.path.join(work, "roomtone.wav")
            M.sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anoisesrc=d={total_len + 1:.2f}:c=pink:a=0.003",
                  "-ar", "48000", "-ac", "2", song])
        ins = ["-i", cut, "-ss", f"{t0:.3f}", "-i", song] + sum((["-i", f] for _, f in vo_at), [])
        fc = ["[0:a]volume=1.0[dlg]",
              f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{total_len:.2f},"
              f"afade=t=in:d=1.2,afade=t=out:st={total_len - 2.5:.2f}:d=2.5,volume={0.28 if kind == "ugc" else 0.6}[sc]"]
        names = []
        for k, (at, _) in enumerate(vo_at):
            ms = int(at * 1000)
            fc.append(f"[{k + 2}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume=1.35[n{k}]")
            names.append(f"[n{k}]")
        if names:
            fc.append("".join(names) + f"amix=inputs={len(names)}:normalize=0[nar]")
            fc.append("[dlg][nar]amix=inputs=2:normalize=0,asplit=2[voice][key]")
        else:
            fc.append("[dlg]asplit=2[voice][key]")
        fc.append("[sc][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        fc.append(f"[voice][duck]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5,atrim=0:{total_len:.2f}[mix]")
        M.sh(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[mix]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])

    poster = out.rsplit(".", 1)[0] + ".jpg"
    M.sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{min(1.2, body / 2):.2f}", "-i", out, "-frames:v", "1",
          "-q:v", "3", poster])
    report.update(duration=round(M.probe_dur(out), 2), balance_end=M.balance(),
                  stills=[r["i"] for r in report["shots"] if r.get("model") == "still"],
                  failed=[r["i"] for r in report["shots"] if r.get("error")])
    json.dump(report, open(out.rsplit(".", 1)[0] + ".json", "w"), indent=2)
    log("done", out, report["duration"], "s  stills:", report["stills"], "failed:", report["failed"])
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("song", help="song file, or - for none (UGC)")
    ap.add_argument("out")
    ap.add_argument("--kind", default="music_video", choices=["music_video", "short_film", "ugc"])
    ap.add_argument("--desc", default="")
    ap.add_argument("--style", default="cinematic", choices=list(STYLES))
    ap.add_argument("--length", type=float, default=60)
    ap.add_argument("--title", default="")
    ap.add_argument("--artist", default="")
    ap.add_argument("--work", default=os.path.join(M.ROOT, "work", "video"))
    ap.add_argument("--brief", help="director's brief json (chapters with shot pools)")
    a = ap.parse_args()
    br = json.load(open(a.brief)) if a.brief else None
    build(a.photo, None if a.song == "-" else a.song, a.out, a.kind, a.desc, a.style, a.length, a.title, a.artist, a.work, brief=br)
