# F5 Studio

A local, offline app for turning study scripts into long-form audio with F5-TTS. Open it from the
Dock (`~/Applications/F5 Studio.app`); quitting it stops everything.

## How it fits together

- `desktop/` — the Mac app: a native window (Swift, WKWebView) like Circle. `build.sh` rebuilds and
  reinstalls it; `make_icon.py` draws the full-bleed icon.
- `run_server.sh` — what the app runs on launch: the backend on `127.0.0.1:8799`, log in `server.log`.
- `studio/` — the backend (FastAPI, in `~/f5-tts/.venv`):
  - `server.py` API + UI, `store.py` files on disk, `textprep.py` script → spoken paragraphs,
    `engine.py` F5 model + generation queue, `export.py` merge → `~/f5-tts/exports/<project>/`, `voices.py` clips,
    `inbox.py` the Cogitator bridge (below), `parts.py` optional splitting of long projects into parts
    (planned once from the generation-time estimate, by whole sections; each part can auto-export when done).
- **The Cogitator bridge** (`studio/inbox.py`): the sidebar's "From the Cogitator" list shows the
  tutor scripts that the Scriptorium in `~/study` saves to `~/study/scripts/`. A script counts as
  ready when the Scriptorium's job (`127.0.0.1:8779/scriptorium/api/job`) is no longer writing it and
  it ends with its sign-off. Import makes it a project, or updates the project made from it before;
  unchanged paragraphs keep their audio. The gear button turns on automatic import (and generation),
  and maps each character to an F5 voice. In a project's Script step, "The Cogitator" picks one of
  these scripts for that project (or imports it as a new project when the open one already has
  its own script or audio; replacing then needs a confirmation), and "Open the Cogitator" brings up its app. F5 Studio only reads
  `~/study`; it never writes there.
- `ui/` — the front end (plain HTML/CSS/JS).

## Where things live

- `~/f5-tts/projects/<id>/` — `project.json`, `script.txt`, `source.txt`, `clips/` (one WAV per
  paragraph; `clips/index.json` maps each paragraph's text to its clip, so editing a line only
  redoes that line).
- `~/f5-tts/studio/voices/<id>/` — `voice.json`, `clip.wav` (trimmed, 24 kHz), `original.*`.
- `~/f5-tts/studio/pronunciations.json` — the shared pronunciation list.
- `~/f5-tts/exports/<project title>/` — exported MP3/WAV files (Show in Finder opens it).

## Notes

- Runs fully offline (`HF_HUB_OFFLINE=1`). One paragraph at a time on the GPU: the installed
  `f5_tts/infer/utils_infer.py` is patched to `ThreadPoolExecutor(max_workers=1)` because
  concurrent batches crash Metal. Reinstalling f5-tts undoes that patch.
- Dev: `cd ~/f5-tts/app && ../.venv/bin/python -m studio.server 8798`, then open
  http://127.0.0.1:8798.
