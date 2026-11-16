"""Merge the finished sections of a part into one WAV, stopping before the first incomplete section.

Usage: merge_partial.py PROJECT_DIR OUT_WAV
"""
import json, sys
from pathlib import Path

import numpy as np
import soundfile as sf

proj, out = Path(sys.argv[1]), Path(sys.argv[2])
SR, GAP_PARA, GAP_AFTER_HEADING, GAP_SECTION = 24000, 0.45, 0.7, 1.3
sections = json.loads((proj / "sections.json").read_text())
silence = lambda s: np.zeros(int(SR * s), dtype=np.float32)

parts, last = [], None
for si, s in enumerate(sections):
    clips = [proj / "clips" / f"s{si:02d}_p{pi:03d}.wav" for pi in range(len(s["paras"]))]
    if not all(c.exists() for c in clips):
        break
    for pi, c in enumerate(clips):
        parts += [sf.read(str(c), dtype="float32")[0], silence(GAP_AFTER_HEADING if si > 0 and pi == 0 else GAP_PARA)]
    parts.append(silence(GAP_SECTION))
    last = s["title"]

merged = np.concatenate(parts)
sf.write(str(out), merged, SR)
print(f"{len(merged)/SR/60:.1f} minutes, through section {si - 1 if last else -1}: {last}")
