"""Adding and trimming reference voices."""
import re, shutil, subprocess, time
from pathlib import Path

from . import engine, store

FFMPEG = "/opt/homebrew/bin/ffmpeg"
MAX_SECS = 12.0


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "voice"
    base, n = s, 2
    while (store.VOICES / s).exists():
        s, n = f"{base}-{n}", n + 1
    return s


def render_clip(vid, start, end):
    """original.* -> clip.wav: mono, 24 kHz, trimmed, light loudness normalising."""
    d = store.VOICES / vid
    src = next(d.glob("original.*"))
    end = min(end, start + MAX_SECS)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.2f}", "-to", f"{end:.2f}",
                    "-i", str(src), "-ac", "1", "-ar", "24000", "-af", "loudnorm=I=-20:TP=-2", str(d / "clip.wav")],
                   check=True)
    return store.audio_duration(d / "clip.wav")


def add(upload_path, filename, name, note=""):
    vid = _slug(name)
    d = store.VOICES / vid
    d.mkdir(parents=True)
    ext = Path(filename).suffix.lower() or ".wav"
    shutil.copy(upload_path, d / f"original{ext}")
    full = float(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(d / f"original{ext}")],
                                capture_output=True, text=True, check=True).stdout.strip() or 0)
    end = min(full, 10.0)
    dur = render_clip(vid, 0.0, end)
    v = {"id": vid, "name": name, "note": note, "dur": round(dur, 1), "source_dur": round(full, 1),
         "trim": [0.0, round(end, 2)], "transcript": engine.transcribe(d / "clip.wav"), "created": time.time()}
    return store.save_voice(v)


def retrim(vid, start, end):
    v = store.voice(vid)
    v["dur"] = round(render_clip(vid, start, end), 1)
    v["trim"] = [round(start, 2), round(min(end, start + MAX_SECS), 2)]
    v["transcript"] = engine.transcribe(store.voice_wav(vid))
    return store.save_voice(v)
