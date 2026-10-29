"""Deep cinematic narrator voice for iRun ads (open-source Kokoro, CPU, free). Original voice — a blend of
Kokoro's deepest male voices, slowed, pitched down with formants kept, warmed and given a little room. It does not
imitate any real person.

  pip install kokoro-onnx soundfile
  (model files: github.com/thewh1teagle/kokoro-onnx releases "model-files-v1.0": kokoro-v1.0.onnx, voices-v1.0.bin
   -> put them in assets/voice/models/ or set KOKORO_DIR)
  python engine/narrator.py assets/voice/<slug> "First line." "Second line." ...
Writes vo1.wav, vo2.wav ... for a trailer spec's "vo" list. Write brand names how they're said ("Flip It").
"""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FX = ("aresample=44100,rubberband=pitch=0.94:formant=preserved,"
      "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
      "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
      "highpass=f=55,equalizer=f=140:t=q:w=1:g=3.5,equalizer=f=3200:t=q:w=1.2:g=-2,equalizer=f=7000:t=q:w=2:g=-3,"
      "acompressor=threshold=-20dB:ratio=3:attack=8:release=120,aecho=0.8:0.5:28|46:0.12|0.07,loudnorm=I=-16:TP=-1.5")


def main(outdir, lines, speed=0.84):
    import soundfile as sf
    from kokoro_onnx import Kokoro
    d = os.environ.get("KOKORO_DIR", os.path.join(ROOT, "assets", "voice", "models"))
    k = Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))
    style = k.get_voice_style("am_onyx") * 0.75 + k.get_voice_style("am_michael") * 0.25
    os.makedirs(outdir, exist_ok=True)
    for i, text in enumerate(lines, 1):
        a, sr = k.create(text, voice=style, speed=speed, lang="en-us")
        raw = os.path.join(outdir, f".raw{i}.wav"); sf.write(raw, a, sr)
        out = os.path.join(outdir, f"vo{i}.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", FX, "-ac", "1", "-ar", "44100", out], check=True)
        os.remove(raw)
        print(f"[narrator] vo{i}.wav  {text}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
