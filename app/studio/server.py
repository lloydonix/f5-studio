"""F5 Studio backend: a local-only HTTP API plus the UI, on 127.0.0.1.

Run: ~/f5-tts/.venv/bin/python -m studio.server 8799   (from ~/f5-tts/app; run_server.sh does this)
"""
import os, subprocess, sys, tempfile
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import engine, export, inbox, parts, store, textprep, voices

UI = Path(__file__).resolve().parent.parent / "ui"
app = FastAPI(title="F5 Studio", docs_url=None, redoc_url=None)


def project_or_404(pid):
    try:
        return store.Project(pid)
    except KeyError:
        raise HTTPException(404, "No such project")


def voice_or_404(vid):
    try:
        return store.voice(vid)
    except KeyError:
        raise HTTPException(404, "No such voice")


def bad(msg, code=400):
    raise HTTPException(code, msg)


# ---------- overview ----------

@app.get("/api/state")
def state():
    return {
        "projects": [p.summary() for p in store.projects()],
        "voices": store.voices(),
        "pronunciations": len(store.pronunciations()),
        "worker": engine.WORKER.state(),
    }


@app.get("/api/status")
def status():
    """Cheap poll while generating: worker state plus the active project's counts."""
    w = engine.WORKER.state()
    out = {"worker": w}
    if w["current"]:
        out["project"] = store.Project(w["current"]["project"]).summary()
    return out


# ---------- projects ----------

@app.post("/api/projects")
def create_project(title: str = Body(...), voice: str = Body(...), persona: str = Body("")):
    if not title.strip():
        bad("Give the project a name.")
    voice_or_404(voice)
    return store.create_project(title.strip(), voice, persona).summary()


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    p = project_or_404(pid)
    sections = p.sections()
    m = p.meta
    return {
        **p.summary(sections), "script": p.script, "source": p.source, "sections": sections,
        "pacing": m["pacing"], "quality": m["quality"], "writer": m["writer"], "origin": m.get("origin"), "exports": p.exports(), "export_dir": str(p.export_dir),
        "check": textprep.fact_check(p.source, p.script) if p.source.strip() else None,
        "split": parts.summary(p, sections, engine.WORKER.ratio),
    }


@app.put("/api/projects/{pid}/script")
def save_script(pid: str, script: str = Body(..., embed=True)):
    p = project_or_404(pid)
    p.save_script(script)
    return get_project(pid)


@app.put("/api/projects/{pid}/source")
def save_source(pid: str, source: str = Body(..., embed=True)):
    p = project_or_404(pid)
    p.save_source(source)
    return {"check": textprep.fact_check(source, p.script) if source.strip() else None}


@app.put("/api/projects/{pid}/settings")
def save_settings(pid: str, body: dict = Body(...)):
    p = project_or_404(pid)
    allowed = {k: body[k] for k in ("title", "voice", "persona", "pacing", "quality", "writer") if k in body}
    if "voice" in allowed:
        voice_or_404(allowed["voice"])
    p.save_meta(**allowed)
    return p.summary()


@app.post("/api/projects/{pid}/regen")
def regen(pid: str, key: str = Body(..., embed=True)):
    p = project_or_404(pid)
    p.drop_clip(key)
    engine.WORKER.enqueue(pid)
    return {"ok": True}


# ---------- generation ----------

@app.post("/api/generate/{pid}/start")
def gen_start(pid: str):
    project_or_404(pid)
    engine.WORKER.start(pid)
    return engine.WORKER.state()


@app.post("/api/generate/pause")
def gen_pause():
    engine.WORKER.pause()
    return engine.WORKER.state()


@app.post("/api/preview")
def preview(text: str = Body(...), voice: str = Body(...), quality: str = Body("best")):
    v = voice_or_404(voice)
    spoken = textprep.speak(text, store.pronunciations())
    if not spoken:
        bad("Type something to hear.")
    return Response(engine.ENGINE.preview_wav_bytes(v, spoken, quality), media_type="audio/wav",
                    headers={"X-Spoken": spoken.encode("ascii", "ignore").decode()})


# ---------- export ----------

@app.post("/api/projects/{pid}/export")
def do_export(pid: str, partial: bool = Body(False), format: str = Body("mp3"),
              quality: str = Body("high"), name: str = Body(""), part: int = Body(0)):
    p = project_or_404(pid)
    try:
        return export.merge(p, partial=partial, fmt=format, quality=quality, name=name or None, part=part or None)
    except ValueError as e:
        bad(str(e))


@app.put("/api/projects/{pid}/split")
def set_split(pid: str, body: dict = Body(...)):
    """{enabled, hours, auto_export, dismissed}: any subset. Turning it on (or changing hours) re-plans the parts."""
    p = project_or_404(pid)
    if "hours" in body and not (0.5 <= float(body["hours"]) <= 48):
        bad("Pick between half an hour and 48 hours.")
    parts.update(p, body, p.sections(), engine.WORKER.ratio)
    return parts.summary(p, p.sections(), engine.WORKER.ratio)


@app.post("/api/projects/{pid}/exports/reveal")
def reveal_exports(pid: str):
    """Open the project's exports folder (~/f5-tts/exports/<title>) in Finder, creating it if needed."""
    p = project_or_404(pid)
    p.export_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/open", str(p.export_dir)])
    return {"path": str(p.export_dir)}


@app.post("/api/reveal")
def reveal(path: str = Body(..., embed=True)):
    f = Path(path).resolve()
    if not f.exists() or not (str(f).startswith(str(store.DOWNLOADS)) or str(f).startswith(str(store.ROOT))):
        bad("Can't show that file.")
    subprocess.run(["/usr/bin/open", "-R", str(f)])
    return {"ok": True}


# ---------- pronunciations ----------

@app.get("/api/pronunciations")
def get_prons():
    return store.pronunciations()


@app.put("/api/pronunciations")
def put_prons(rows: list = Body(...)):
    return store.save_pronunciations(rows)


# ---------- voices ----------

@app.post("/api/voices")
async def add_voice(file: UploadFile = File(...), name: str = Form(...), note: str = Form("")):
    if not name.strip():
        bad("Give the voice a name.")
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "clip.wav").suffix, delete=False) as tmp:
        tmp.write(await file.read())
    try:
        return voices.add(tmp.name, file.filename or "clip.wav", name.strip(), note.strip())
    except subprocess.CalledProcessError:
        bad("Couldn't read that audio file.")
    finally:
        os.unlink(tmp.name)


@app.put("/api/voices/{vid}")
def update_voice(vid: str, body: dict = Body(...)):
    v = voice_or_404(vid)
    for k in ("name", "note", "transcript"):
        if k in body:
            v[k] = body[k]
    return store.save_voice(v)


@app.post("/api/voices/{vid}/trim")
def trim_voice(vid: str, start: float = Body(...), end: float = Body(...)):
    voice_or_404(vid)
    if end - start < 2:
        bad("Keep at least 2 seconds.")
    return voices.retrim(vid, start, end)


@app.post("/api/voices/{vid}/transcribe")
def retranscribe(vid: str):
    v = voice_or_404(vid)
    v["transcript"] = engine.transcribe(store.voice_wav(vid))
    return store.save_voice(v)


# ---------- the Cogitator (scripts from ~/study's Scriptorium) ----------

@app.get("/api/cogitator")
def cogitator():
    return {**inbox.scan(), "settings": inbox.settings()}


@app.post("/api/cogitator/open")
def cogitator_open():
    inbox.open_cogitator()
    return {"ok": True}


@app.put("/api/cogitator/settings")
def cogitator_settings(body: dict = Body(...)):
    return inbox.save_settings(body)


@app.post("/api/cogitator/import")
def cogitator_import(name: str = Body(...), voice: str = Body(""), generate: bool = Body(False),
                     project: str = Body(""), replace: bool = Body(False)):
    if voice:
        voice_or_404(voice)
    if project:
        project_or_404(project)
    try:
        return inbox.import_script(name, voice or None, generate, project or None, replace)
    except FileNotFoundError:
        bad("That script isn't in the Cogitator's folder anymore.", 404)
    except PermissionError as e:
        bad(str(e), 409)
    except ValueError as e:
        bad(str(e))


# ---------- files ----------

@app.get("/media/projects/{pid}/clips/{name}")
def clip(pid: str, name: str):
    f = (store.PROJECTS / pid / "clips" / name).resolve()
    if f.parent != (store.PROJECTS / pid / "clips").resolve() or not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="audio/wav")


@app.get("/media/voices/{vid}.wav")
def voice_audio(vid: str):
    voice_or_404(vid)
    return FileResponse(store.voice_wav(vid), media_type="audio/wav")


@app.get("/media/voices/{vid}/original")
def voice_original(vid: str):
    voice_or_404(vid)
    f = next((store.VOICES / vid).glob("original.*"))
    return FileResponse(f)


@app.get("/")
def root():
    return RedirectResponse("/app/ui/index.html")


app.mount("/app/ui", StaticFiles(directory=UI), name="ui")


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    # Short graceful shutdown: the app window's keep-alive connections would otherwise hold the
    # port open after Quit, and a quick reopen would find a dying server.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=3)
