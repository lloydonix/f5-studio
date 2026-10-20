"""The Cogitator bridge: tutor scripts written by the Scriptorium (~/study) come into F5 Studio.

The Scriptorium saves `~/study/scripts/<Voice> Tutor Script - <Subject> - Part N.txt`, appending each
section as it's written. A script is ready once the Scriptorium's job no longer lists it as the file in
progress (its API, 127.0.0.1:8779) and it ends with the closing sign-off. Ready scripts can be imported
as projects by hand, or automatically (with an optional start of generation).

Read-only toward ~/study: this never writes there.
"""
import re, threading, time
from pathlib import Path

import httpx

from . import engine, store

SCRIPTS = Path.home() / "study" / "scripts"
JOB_API = "http://127.0.0.1:8779/scriptorium/api/job"
SETTINGS = store.STUDIO / "cogitator.json"
BAR = re.compile(r"^={10,}$")
NAME = re.compile(r"^(?P<voice>.+?) Tutor Script - (?P<subject>.+?) - (?P<label>.+)\.txt$")

_lock = threading.Lock()


def settings():
    s = store._read(SETTINGS, {}) or {}
    s.setdefault("auto_import", False)
    s.setdefault("auto_generate", False)
    s.setdefault("voice_map", {})          # Cogitator persona -> F5 voice id
    return s


def save_settings(change):
    s = settings()
    for k in ("auto_import", "auto_generate", "voice_map"):
        if k in change:
            s[k] = change[k]
    store._write(SETTINGS, s)
    return s


def _job():
    try:
        return httpx.get(JOB_API, timeout=1.5).json()
    except Exception:
        return None   # the Cogitator isn't running


def _finished(text):
    """True when the file ends with the closing sign-off: its last ===== line isn't part of a heading."""
    lines = text.rstrip().splitlines()
    bars = [i for i, l in enumerate(lines) if BAR.match(l.strip())]
    if len(bars) < 3:
        return False
    i = bars[-1]
    heading = (i >= 2 and BAR.match(lines[i - 2].strip())) or (i + 2 < len(lines) and BAR.match(lines[i + 2].strip()))
    return not heading and i < len(lines) - 1


def _imported():
    """Cogitator file name -> (project, the file mtime it was imported at)."""
    out = {}
    for p in store.projects():
        o = p.meta.get("origin") or {}
        if o.get("cogitator"):
            out[o["cogitator"]] = (p, o.get("mtime", 0))
    return out


def scan():
    if not SCRIPTS.is_dir():
        return {"available": False, "folder": str(SCRIPTS), "items": [], "job": None}
    job = _job()
    writing = job["files"][-1] if job and job.get("state") == "running" and job.get("files") else None
    stopped = job["files"][-1] if job and job.get("state") in ("failed", "cancelled") and job.get("files") else None
    done = _imported()
    items = []
    for f in sorted(SCRIPTS.glob("*.txt"), key=lambda f: -f.stat().st_mtime):
        st = f.stat()
        m = NAME.match(f.name)
        text = f.read_text(encoding="utf-8", errors="replace")
        if f.name == writing:
            state = "writing"
        elif f.name == stopped or not _finished(text):
            state = "incomplete"
        else:
            state = "ready"
        proj, at = done.get(f.name, (None, 0))
        items.append({
            "name": f.name, "size": st.st_size, "modified": st.st_mtime, "state": state,
            "voice": m["voice"] if m else "", "subject": m["subject"] if m else f.stem,
            "label": m["label"] if m else "", "words": len(text.split()),
            "project": proj.id if proj else None,
            "changed": bool(proj) and st.st_mtime > at + 1,
        })
    return {"available": True, "folder": str(SCRIPTS), "items": items,
            "job": job and {k: job.get(k) for k in ("state", "done", "total", "files")}}


def open_cogitator():
    """Bring up The Cogitator app (its Scriptorium is in Open WebUI's sidebar there)."""
    import subprocess
    r = subprocess.run(["/usr/bin/open", "-b", "com.lloyd.study"], capture_output=True)
    if r.returncode:
        subprocess.run(["/usr/bin/open", "http://127.0.0.1:8779/scriptorium"])


def import_script(name, voice_id=None, generate=False, project_id=None):
    """Create a project from a Cogitator script, or update the one made from it before.
    With project_id, the script goes into that project instead (and links it to the file)."""
    f = SCRIPTS / Path(name).name
    if not f.is_file():
        raise FileNotFoundError(name)
    m = NAME.match(f.name)
    persona = m["voice"] if m else ""
    with _lock:
        proj = store.Project(project_id) if project_id else _imported().get(f.name, (None, 0))[0]
        if project_id and persona and not proj.meta.get("persona"):
            proj.save_meta(persona=persona)
        if not proj:
            vmap = settings()["voice_map"]
            voice_id = voice_id or vmap.get(persona) or (store.voices()[0]["id"] if store.voices() else None)
            if not voice_id:
                raise ValueError("Add a voice in F5 Studio first.")
            title = f"{m['subject']} · {m['label']}" if m else f.stem
            proj = store.create_project(title, voice_id, persona)
        elif voice_id and voice_id != proj.meta.get("voice"):
            proj.save_meta(voice=voice_id)
        proj.save_script(f.read_text(encoding="utf-8"))
        proj.save_meta(origin={"cogitator": f.name, "mtime": f.stat().st_mtime, "imported": time.time()})
    if generate:
        w = engine.WORKER.state()
        (engine.WORKER.enqueue if w["running"] else engine.WORKER.start)(proj.id)
    return proj.summary()


def _auto_loop():
    while True:
        time.sleep(15)
        try:
            s = settings()
            if not s["auto_import"]:
                continue
            for it in scan()["items"]:
                if it["state"] == "ready" and (not it["project"] or it["changed"]):
                    import_script(it["name"], generate=s["auto_generate"])
                    print(f"cogitator: imported {it['name']}", flush=True)
        except Exception as e:
            print(f"cogitator: auto-import skipped: {type(e).__name__}: {e}", flush=True)


threading.Thread(target=_auto_loop, daemon=True, name="cogitator-inbox").start()
