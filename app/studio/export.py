"""Merge a project's paragraph clips into one file in ~/f5-tts/exports/<project title>/."""
import re, subprocess, time
from pathlib import Path

import numpy as np
import soundfile as sf

from . import store

SR = 24000
MP3_Q = {"high": "2", "standard": "4", "small": "6"}   # LAME VBR quality


def plan(project, partial):
    """Clips to merge, in order. Partial stops before the first section with a missing paragraph."""
    sections = project.sections()
    out = []
    for s in sections:
        if any(not p["dur"] for p in s["paras"]):
            if partial:
                break
            raise ValueError("Some paragraphs aren't generated yet. Export the finished sections instead.")
        out.append(s)
    return out


def merge(project, partial=False, fmt="mp3", quality="high", name=None, part=None):
    """part: export only that part of a split project (see parts.py), named "<title> - Part n of N"."""
    from . import parts as parts_mod
    sig = None
    if part:
        all_sections = project.sections()
        rng = {n: (a, b) for n, a, b in parts_mod.ranges(project, all_sections)}
        if part not in rng:
            raise ValueError("That part doesn't exist.")
        a, b = rng[part]
        sections = all_sections[a:b + 1]
        if any(not p["dur"] for s in sections for p in s["paras"]):
            raise ValueError(f"Part {part} isn't finished yet.")
        sig = parts_mod.signature(all_sections, a, b)
        name = name or f"{project.meta.get('title', project.id)} - Part {part} of {len(rng)}"
    else:
        sections = plan(project, partial)
    if not sections:
        raise ValueError("No complete sections to export yet.")
    gap = project.meta["pacing"]
    silence = lambda s: np.zeros(int(SR * s), dtype=np.float32)
    parts = []
    for s in sections:
        for p in s["paras"]:
            f = project.clip_dir / store_file(project, p["key"])
            a, sr = sf.read(str(f), dtype="float32")
            parts += [a, silence(gap["heading"] if p["heading"] else gap["para"])]
        parts.append(silence(gap["section"]))
    audio = np.concatenate(parts)

    name = re.sub(r'[/:\\]', "-", (name or project.meta.get("title", project.id)).strip()) or project.id
    folder = project.export_dir
    folder.mkdir(parents=True, exist_ok=True)
    wav = project.dir / "export.wav"
    sf.write(str(wav), audio, SR)
    if fmt == "wav":
        out = folder / f"{name}.wav"
        wav.replace(out)
    else:
        out = folder / f"{name}.mp3"
        subprocess.run(["/opt/homebrew/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                        "-c:a", "libmp3lame", "-q:a", MP3_Q.get(quality, "2"), str(out)], check=True)
        wav.unlink()

    total = sum(len(s["paras"]) for s in project.sections())
    rec = {"path": str(out), "name": out.name, "secs": round(len(audio) / SR, 1), "partial": partial,
           "sections": len(sections), "when": time.time(), "format": fmt, "part": part}
    exports = [e for e in project.meta.get("exports", []) if e["path"] != str(out)]
    project.save_meta(exports=[rec] + exports[:19])
    if part:
        parts_mod.mark_exported(project, part, sig)
    rec["of_total"] = total
    return rec


def store_file(project, key):
    return project.clip_index()[key]["file"]
