"""Projects, voices and the pronunciation list, all stored as plain files under ~/f5-tts.

projects/<id>/project.json   title, voice, persona, pacing, where the script comes from
projects/<id>/script.txt     the script as written
projects/<id>/source.txt     optional source notes, for the fact check
projects/<id>/clips/         one WAV per paragraph; index.json maps clip key -> file
studio/voices/<id>/          voice.json + clip.wav (24 kHz mono)
studio/pronunciations.json   [{term, say}], shared by every project
"""
import hashlib, json, re, threading, time
from pathlib import Path

import soundfile as sf

from . import textprep

ROOT = Path.home() / "f5-tts"
PROJECTS = ROOT / "projects"
STUDIO = ROOT / "studio"
VOICES = STUDIO / "voices"
PRON_FILE = STUDIO / "pronunciations.json"
DOWNLOADS = Path.home() / "Downloads"   # older exports went here; still allowed for Show in Finder
EXPORTS = ROOT / "exports"              # exports/<project title>/<file>.mp3

DEFAULT_PACING = {"para": 0.45, "heading": 0.7, "section": 1.3}
_lock = threading.RLock()


def _read(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(p)


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "project"
    base, n = s, 2
    while (PROJECTS / s).exists():
        s, n = f"{base}-{n}", n + 1
    return s


def clip_key(voice_id, text):
    return hashlib.sha1(f"{voice_id}\n{text}".encode()).hexdigest()[:16]


# ---------- pronunciations ----------

def pronunciations():
    return _read(PRON_FILE, [])


def save_pronunciations(rows):
    clean = [{"term": r["term"], "say": r["say"]} for r in rows if r.get("term")]
    with _lock:
        _write(PRON_FILE, clean)
    return clean


# ---------- voices ----------

def voices():
    out = []
    for d in sorted(VOICES.glob("*/voice.json")):
        v = _read(d)
        if v:
            out.append(v)
    return out


def voice(vid):
    v = _read(VOICES / vid / "voice.json")
    if not v:
        raise KeyError(vid)
    return v


def voice_wav(vid):
    return VOICES / vid / "clip.wav"


def save_voice(v):
    with _lock:
        _write(VOICES / v["id"] / "voice.json", v)
    return v


# ---------- projects ----------

class Project:
    def __init__(self, pid):
        self.id = pid
        self.dir = PROJECTS / pid
        if not (self.dir / "project.json").exists():
            raise KeyError(pid)

    @property
    def meta(self):
        m = _read(self.dir / "project.json", {})
        m.setdefault("pacing", dict(DEFAULT_PACING))
        m.setdefault("quality", "best")
        m.setdefault("writer", {"mode": "paste"})   # paste | cogitator
        return m

    def save_meta(self, **changes):
        with _lock:
            m = self.meta
            m.update(changes)
            m["updated"] = time.time()
            _write(self.dir / "project.json", m)
        return m

    @property
    def script(self):
        p = self.dir / "script.txt"
        return p.read_text() if p.exists() else ""

    def save_script(self, text):
        (self.dir / "script.txt").write_text(text)
        self.save_meta()

    @property
    def source(self):
        p = self.dir / "source.txt"
        return p.read_text() if p.exists() else ""

    def save_source(self, text):
        (self.dir / "source.txt").write_text(text)

    # clips
    @property
    def clip_dir(self):
        return self.dir / "clips"

    def clip_index(self):
        return _read(self.clip_dir / "index.json", {})

    def add_clip(self, key, filename, dur, gen_secs):
        with _lock:
            idx = self.clip_index()
            idx[key] = {"file": filename, "dur": round(dur, 2), "gen": round(gen_secs, 1)}
            _write(self.clip_dir / "index.json", idx)

    def drop_clip(self, key):
        with _lock:
            idx = self.clip_index()
            idx.pop(key, None)
            _write(self.clip_dir / "index.json", idx)

    def sections(self):
        """Parsed sections, each paragraph with its clip key and clip info if generated."""
        voice_id = self.meta.get("voice", "")
        idx = self.clip_index()
        out = []
        for si, s in enumerate(textprep.parse(self.script, pronunciations())):
            paras = []
            for pi, text in enumerate(s["paras"]):
                k = clip_key(voice_id, text)
                c = idx.get(k)
                if c and not (self.clip_dir / c["file"]).exists():
                    c = None
                paras.append({"si": si, "pi": pi, "text": text, "key": k,
                              "dur": c["dur"] if c else None,
                              "clip": f"/media/projects/{self.id}/clips/{c['file']}" if c else None,
                              "heading": si > 0 and pi == 0})
            out.append({"title": s["title"], "paras": paras})
        return out

    def summary(self, sections=None):
        sections = sections if sections is not None else self.sections()
        paras = [p for s in sections for p in s["paras"]]
        m = self.meta
        return {
            "id": self.id, "title": m.get("title", self.id), "voice": m.get("voice"),
            "persona": m.get("persona", ""), "updated": m.get("updated", 0),
            "words": sum(len(p["text"].split()) for p in paras),
            "done": sum(1 for p in paras if p["dur"]), "total": len(paras),
            "audio": round(sum(p["dur"] or 0 for p in paras), 1),
        }

    @property
    def export_dir(self):
        name = re.sub(r'[/:\\]', '-', self.meta.get('title', self.id)).strip(' .') or self.id
        return EXPORTS / name

    def exports(self):
        return [e for e in self.meta.get("exports", []) if Path(e["path"]).exists()]


def projects():
    out = []
    for f in PROJECTS.glob("*/project.json"):
        try:
            out.append(Project(f.parent.name))
        except KeyError:
            pass
    return sorted(out, key=lambda p: (p.meta.get("order", 999), p.meta.get("title", "")))


def create_project(title, voice_id, persona=""):
    pid = slugify(title)
    d = PROJECTS / pid
    (d / "clips").mkdir(parents=True)
    _write(d / "project.json", {"title": title, "voice": voice_id, "persona": persona,
                                "created": time.time(), "updated": time.time(),
                                "pacing": dict(DEFAULT_PACING), "order": 100})
    (d / "script.txt").write_text("")
    return Project(pid)


def audio_duration(path):
    return sf.info(str(path)).duration
