"""One-time setup: turn the hand-run Shadowheart projects into F5 Studio projects.

Adds project.json, script.txt, source.txt and clips/index.json to projects/shadowheart{,2,3,4};
creates the Vivian voice and studio/pronunciations.json. Existing clips are reused, never moved.
Run from ~/projects/f5-tts/app:  ../.venv/bin/python -m tools.migrate
"""
import ast, json, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from studio import store, textprep  # noqa: E402

DL = Path.home() / "Downloads"
PROJECTS = [
    ("shadowheart", "Civ Pro I · Part 1", "Shadowheart", 1,
     "Shadowheart Tutor Script - Civil Procedure I JDN 201.txt", None),
    ("shadowheart2", "Civ Pro I · Part 2", "Shadowheart (dom)", 2,
     "Shadowheart Tutor Script - Part 2 Midterm Carryover - Civil Procedure I JDN 201.txt", "part2_script_dom.txt"),
    ("shadowheart3", "Civ Pro I · Part 3", "Shadowheart (dom)", 3,
     "Shadowheart Tutor Script - Part 3 Finals Coverage - Civil Procedure I JDN 201.txt", "part3_script_dom.txt"),
    ("shadowheart4", "Civ Pro I · Part 4 Cheat Sheet", "Shadowheart (dom)", 4,
     "Part 4 Condensed Cheat Sheet - Civil Procedure I JDN 201.txt", "part4_script_dom.txt"),
]
VIVIAN_TEXT = ("This is Lloyd's friend, Vivian. How are you doing today? I just got back from the library "
               "and I'm currently making me some hot coffee.")


def pronunciations():
    src = (store.PROJECTS / "shadowheart/clean_script.py").read_text()
    pairs = ast.literal_eval(re.search(r"REPL = (\[.*?\n\])", src, re.S).group(1))
    rows, seen = [], set()
    for a, b in pairs:
        if a not in seen and a != b:
            seen.add(a)
            rows.append({"term": a, "say": b})
    if not store.PRON_FILE.exists():
        store.save_pronunciations(rows)
    print(f"pronunciations: {len(store.pronunciations())}")


def vivian():
    d = store.VOICES / "vivian"
    if (d / "voice.json").exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(store.ROOT / "voices/kiki.wav", d / "clip.wav")
    orig = DL / "kikivoice-cloned-file-2026-10-13-23-24-11-1369.mp3"
    shutil.copy(orig if orig.exists() else d / "clip.wav", d / ("original.mp3" if orig.exists() else "original.wav"))
    dur = round(store.audio_duration(d / "clip.wav"), 1)
    store.save_voice({"id": "vivian", "name": "Vivian", "note": "UK, calm and chatty", "dur": dur, "source_dur": dur,
                      "trim": [0.0, dur], "transcript": VIVIAN_TEXT, "created": 0})
    print("voice: vivian")


def project(pid, title, persona, order, source_name, script_name):
    d = store.PROJECTS / pid
    src = (DL / source_name).read_text()
    script = (d / script_name).read_text() if script_name else src
    if not (d / "project.json").exists():
        store._write(d / "project.json", {"title": title, "voice": "vivian", "persona": persona, "order": order,
                                          "created": 0, "updated": 0, "pacing": dict(store.DEFAULT_PACING)})
    (d / "script.txt").write_text(script)
    (d / "source.txt").write_text(src)

    # Map each paragraph's new clip key to the clip that was generated for that position.
    old = json.loads((d / "sections.json").read_text())
    new = textprep.parse(script, store.pronunciations())
    idx = json.loads((d / "clips/index.json").read_text()) if (d / "clips/index.json").exists() else {}
    mapped = mismatched = 0
    for si, s in enumerate(new):
        if si >= len(old) or len(old[si]["paras"]) != len(s["paras"]):
            mismatched += len(s["paras"])
            continue
        for pi, text in enumerate(s["paras"]):
            f = d / "clips" / f"s{si:02d}_p{pi:03d}.wav"
            if f.exists():
                idx[store.clip_key("vivian", text)] = {"file": f.name, "dur": round(store.audio_duration(f), 2), "gen": 0}
                mapped += 1
    store._write(d / "clips/index.json", idx)
    total = sum(len(s["paras"]) for s in new)
    print(f"{pid}: {mapped}/{total} paragraphs mapped to existing clips"
          + (f", {mismatched} in sections whose layout changed" if mismatched else ""))


if __name__ == "__main__":
    pronunciations()
    vivian()
    for p in PROJECTS:
        project(*p)
