"""Owner voice for iRun ads: clone Elvin's own voice (open-source Chatterbox, runs on CPU) from
assets/voice/elvin_ref.wav and record each voiceover line. No ElevenLabs, no stock AI voices.

  pip install chatterbox-tts faster-whisper
  python engine/myvoice.py assets/voice/<slug> "First line." "Second line." ...
Writes vo1.wav, vo2.wav ... (trimmed, loudness-normalized, 44.1 kHz) into the folder, making 2 takes per line and
keeping the one whose transcript best matches the text. Reference in a trailer spec with
  "vo": [{"file": "assets/voice/<slug>/vo1.wav", "at": 0.25, "text": "First line."}, ...]
Tip: spell words the way they're said if a take mispronounces them ("tax leen", "Flip It").
"""
import difflib
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REF = os.path.join(ROOT, "assets", "voice", "elvin_ref.wav")


def _score(path, text, stt):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    heard = " ".join(s.text for s in stt.transcribe(a)[0]).lower()
    return difflib.SequenceMatcher(None, heard, text.lower()).ratio()


def main(outdir, lines, takes=2):
    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    from faster_whisper import WhisperModel
    torch.set_num_threads(os.cpu_count() or 2)
    os.makedirs(outdir, exist_ok=True)
    tts = ChatterboxTTS.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
    stt = WhisperModel("small.en", device="cpu", compute_type="int8")
    for i, text in enumerate(lines, 1):
        best = None
        for k in range(takes):
            tmp = os.path.join(outdir, f".take{i}_{k}.wav")
            wav = tts.generate(text, audio_prompt_path=REF, exaggeration=0.55, cfg_weight=0.45, temperature=0.75)
            ta.save(tmp, wav, tts.sr)
            sc = _score(tmp, text, stt)
            if not best or sc > best[0]:
                best = (sc, tmp)
        out = os.path.join(outdir, f"vo{i}.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", best[1], "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,"
                        "highpass=f=60,loudnorm=I=-16:TP=-1.5", "-ar", "44100", "-ac", "1", out], check=True)
        for f in os.listdir(outdir):
            if f.startswith(f".take{i}_"):
                os.remove(os.path.join(outdir, f))
        print(f"[voice] vo{i}.wav  match {best[0]:.2f}  {text}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
