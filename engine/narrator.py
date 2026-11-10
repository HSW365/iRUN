"""Cinematic narrator for iRun ads — free and open-source, human-sounding.

Engine: Chatterbox (Resemble AI, MIT) — expressive, emotion-controlled speech with natural breath and pacing.
Every line is recorded in several takes; Whisper transcribes each take and the cleanest, most accurate one is kept.
The narrator is one consistent original voice (assets/voice/narrator_ref.wav). It does not imitate any real person.
If that reference is missing it is created once from Kokoro's deepest male voice, then Chatterbox performs every
line in that timbre — so all ads share the same narrator.

  pip install chatterbox-tts faster-whisper kokoro-onnx soundfile
  python engine/narrator.py assets/voice/<slug> "First line." "Second line." ...
Writes vo1.wav, vo2.wav ... for a trailer spec. Write brand names how they're said ("Flip It", "H S W three sixty five").

Tuning (env): IRUN_VO_TAKES (3), IRUN_VO_EXAG (0.62 — drama), IRUN_VO_CFG (0.32 — lower = slower, weightier delivery),
IRUN_VO_TEMP (0.7). IRUN_NARRATOR=kokoro forces the old lightweight voice.
"""
import difflib
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REF = os.environ.get("IRUN_NARRATOR_REF") or os.path.join(ROOT, "assets", "voice", "narrator_ref.wav")
KOKORO_DIR = os.environ.get("KOKORO_DIR", os.path.join(ROOT, "assets", "voice", "models"))

# Clean broadcast polish: no pitch-shifting, no echo — those are what made the old voice sound synthetic.
TRIM = ("silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.04,areverse,"
        "silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.12,areverse")
POLISH = (TRIM + ",highpass=f=70,lowpass=f=15000,"
          "equalizer=f=110:t=q:w=0.9:g=2.5,equalizer=f=350:t=q:w=1.2:g=-1.5,"
          "equalizer=f=4000:t=q:w=1.5:g=1.5,equalizer=f=7500:t=q:w=2:g=-2.5,"
          "acompressor=threshold=-22dB:ratio=2.5:attack=10:release=150:makeup=2,"
          "alimiter=limit=0.89,loudnorm=I=-15:TP=-1.5:LRA=7")

# Per-ad narrator (set by trailer_job from the spec): IRUN_NARRATOR_BLEND "bm_george:0.65,bm_daniel:0.35",
# IRUN_NARRATOR_TONE deep|bright, IRUN_NARRATOR_SPEED. Each ad builds its own reference so no two ads share a voice.
BRIGHT_POLISH = (TRIM + ",highpass=f=90,lowpass=f=16000,"
                 "equalizer=f=200:t=q:w=1.0:g=-1.5,equalizer=f=3200:t=q:w=1.4:g=2.2,equalizer=f=9500:t=q:w=2:g=1.5,"
                 "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=140:makeup=2,"
                 "alimiter=limit=0.89,loudnorm=I=-15:TP=-1.5:LRA=7")
if os.environ.get("IRUN_NARRATOR_TONE") == "bright":
    POLISH = BRIGHT_POLISH


def _blend():
    spec = os.environ.get("IRUN_NARRATOR_BLEND") or "am_onyx:0.8,am_michael:0.2"
    return [(v.split(":")[0], float(v.split(":")[1]) if ":" in v else 1.0) for v in spec.split(",")]


def _style(k):
    st = None
    for name, w in _blend():
        part = k.get_voice_style(name) * w
        st = part if st is None else st + part
    return st


def _lang():
    return "en-gb" if _blend()[0][0].startswith("b") else "en-us"


def _speed(default=0.9):
    return float(os.environ.get("IRUN_NARRATOR_SPEED") or default)


REF_TEXT = ("Some stories are written in comfort. Mine was written in the streets, on the court, and in uniform. "
            "Every setback taught me something. Now I build for the people who were counted out.")


def _ffmpeg(src, af, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af", af, "-ac", "1", "-ar", "44100", out], check=True)


def _kokoro():
    from kokoro_onnx import Kokoro
    return Kokoro(os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx"), os.path.join(KOKORO_DIR, "voices-v1.0.bin"))


def make_reference():
    """Build the house narrator reference once (deep, warm, unprocessed timbre for Chatterbox to perform in)."""
    import soundfile as sf
    k = _kokoro()
    a, sr = k.create(REF_TEXT, voice=_style(k), speed=_speed(), lang=_lang())
    os.makedirs(os.path.dirname(REF), exist_ok=True)
    raw = REF + ".raw.wav"
    sf.write(raw, a, sr)
    _ffmpeg(raw, TRIM + ",highpass=f=60,loudnorm=I=-18:TP=-2", REF)
    os.remove(raw)
    print(f"[narrator] built house reference {REF}")


def _clean(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower())


def _score(path, text, stt):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if len(a) < 1600:
        return 0.0
    heard = " ".join(s.text for s in stt.transcribe(a, beam_size=1)[0])
    acc = difflib.SequenceMatcher(None, _clean(heard), _clean(text)).ratio()
    # penalise takes that run long for the text (stumbles, repeats, dead air)
    secs, words = len(a) / 16000, max(1, len(text.split()))
    pace = secs / words
    return acc - (0.15 if pace > 0.75 else 0) - (0.1 if pace < 0.22 else 0)


def _chatterbox(outdir, lines):
    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    from faster_whisper import WhisperModel
    if not os.path.exists(REF):
        make_reference()
    torch.set_num_threads(os.cpu_count() or 2)
    tts = ChatterboxTTS.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
    stt = WhisperModel("base.en", device="cpu", compute_type="int8")
    takes = int(os.environ.get("IRUN_VO_TAKES", "3"))
    exag = float(os.environ.get("IRUN_VO_EXAG", "0.62"))
    cfg = float(os.environ.get("IRUN_VO_CFG", "0.32"))
    temp = float(os.environ.get("IRUN_VO_TEMP", "0.7"))
    os.makedirs(outdir, exist_ok=True)
    for i, text in enumerate(lines, 1):
        best = None
        for k in range(takes):
            tmp = os.path.join(outdir, f".take{i}_{k}.wav")
            wav = tts.generate(text, audio_prompt_path=REF, exaggeration=exag, cfg_weight=cfg, temperature=temp)
            ta.save(tmp, wav, tts.sr)
            sc = _score(tmp, text, stt)
            if not best or sc > best[0]:
                best = (sc, tmp)
            if sc > 0.97:
                break
        out = os.path.join(outdir, f"vo{i}.wav")
        _ffmpeg(best[1], POLISH, out)
        for f in os.listdir(outdir):
            if f.startswith(f".take{i}_"):
                os.remove(os.path.join(outdir, f))
        print(f"[narrator] vo{i}.wav  match {best[0]:.2f}  {text}")


def _kokoro_lines(outdir, lines, speed=None):
    import soundfile as sf
    k = _kokoro()
    speed = speed or _speed()
    style = _style(k)
    os.makedirs(outdir, exist_ok=True)
    for i, text in enumerate(lines, 1):
        a, sr = k.create(text, voice=style, speed=speed, lang=_lang())
        raw = os.path.join(outdir, f".raw{i}.wav")
        sf.write(raw, a, sr)
        _ffmpeg(raw, POLISH, os.path.join(outdir, f"vo{i}.wav"))
        os.remove(raw)
        print(f"[narrator:kokoro] vo{i}.wav  {text}")


def main(outdir, lines, speed=None):
    if os.environ.get("IRUN_NARRATOR") != "kokoro":
        try:
            return _chatterbox(outdir, lines)
        except ImportError as e:
            print(f"[narrator] Chatterbox not installed ({e}); using Kokoro")
    return _kokoro_lines(outdir, lines)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
