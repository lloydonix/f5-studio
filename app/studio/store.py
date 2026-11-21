"""Projects, voices and the pronunciation list, all stored as plain files under ~/projects/f5-tts.

projects/<id>/project.json   title, voice, persona, pacing, where the script comes from
projects/<id>/script.txt     the script as written
projects/<id>/source.txt     optional original text, for "Compare with the original"
projects/<id>/clips/         one WAV per paragraph; index.json maps clip key -> file
studio/voices/<id>/          voice.json + clip.wav (24 kHz mono)
studio/pronunciations/       pronunciation lists; each project picks the ones it uses
studio/pronunciations.json   the old single shared list (kept; copied into pronunciations/law.json)
"""
import hashlib, json, re, threading, time
from pathlib import Path

import soundfile as sf

from . import textprep

ROOT = Path.home() / "projects" / "f5-tts"
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


# ---------- pronunciation lists ----------
# Each list is studio/pronunciations/<id>.json: {id, name, terms: [{term, say}], acronyms: [...]}.
# A project picks which lists apply to it. Acronyms are spelled out letter by letter as whole words.

PRON_DIR = STUDIO / "pronunciations"
LAW_ACRONYMS = ["JDR", "ADR", "SPA", "MRs", "MR", "SC", "PNB", "IRAS", "LED", "FEC", "RTC", "MTC", "TRO"]
LEGACY_LISTS = ["law"]          # projects made before lists existed keep the law list (same audio as before)


def _migrate_prons():
    """One time: the old single shared list becomes the 'Law & Latin' list, plus an empty 'General' one."""
    if PRON_DIR.exists():
        return
    with _lock:
        PRON_DIR.mkdir(parents=True, exist_ok=True)
        if PRON_FILE.exists():
            _write(PRON_DIR / "law.json", {"id": "law", "name": "Law & Latin",
                                           "terms": _read(PRON_FILE, []), "acronyms": LAW_ACRONYMS})
        _write(PRON_DIR / "general.json", {"id": "general", "name": "General", "terms": [], "acronyms": []})


def pron_lists():
    _migrate_prons()
    out = []
    for f in sorted(PRON_DIR.glob("*.json")):
        d = _read(f)
        if d:
            d.setdefault("terms", []); d.setdefault("acronyms", [])
            out.append(d)
    return sorted(out, key=lambda d: (d["id"] != "general", d["name"].lower()))


def pron_list(lid):
    _migrate_prons()
    d = _read(PRON_DIR / f"{Path(lid).name}.json")
    if not d:
        raise KeyError(lid)
    d.setdefault("terms", []); d.setdefault("acronyms", [])
    return d


def save_pron_list(lid, name=None, terms=None, acronyms=None):
    with _lock:
        d = pron_list(lid)
        if name is not None and name.strip():
            d["name"] = name.strip()
        if terms is not None:
            d["terms"] = [{"term": r["term"], "say": r["say"]} for r in terms if r.get("term")]
        if acronyms is not None:
            d["acronyms"] = sorted({a.strip() for a in acronyms if a.strip()}, key=lambda a: (-len(a), a))
        _write(PRON_DIR / f"{d['id']}.json", d)
    return d


def create_pron_list(name):
    _migrate_prons()
    lid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "list"
    base, n = lid, 2
    while (PRON_DIR / f"{lid}.json").exists():
        lid, n = f"{base}-{n}", n + 1
    d = {"id": lid, "name": name.strip() or lid, "terms": [], "acronyms": []}
    with _lock:
        _write(PRON_DIR / f"{lid}.json", d)
    return d


def delete_pron_list(lid):
    f = PRON_DIR / f"{Path(lid).name}.json"
    if lid == "general" or not f.exists():
        raise KeyError(lid)
    f.unlink()


def merged_prons(list_ids):
    """(terms, acronyms) from the given lists, in order; a term in an earlier list wins."""
    terms, seen, acr = [], set(), []
    for lid in list_ids:
        try:
            d = pron_list(lid)
        except KeyError:
            continue
        for r in d["terms"]:
            if r["term"] not in seen:
                seen.add(r["term"]); terms.append(r)
        acr += [a for a in d["acronyms"] if a not in acr]
    return terms, acr


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
        m.setdefault("pron_lists", list(LEGACY_LISTS))
        return m

    def prons(self):
        return merged_prons(self.meta["pron_lists"])

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
        terms, acronyms = self.prons()
        for si, s in enumerate(textprep.parse(self.script, terms, acronyms)):
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
    # Newest first. Projects without a creation time (the migrated Civ Pro parts) go by their part
    # order, last part first, below anything created in the app.
    return sorted(out, key=lambda p: (-(p.meta.get("created") or 0), -(p.meta.get("order") or 0), p.meta.get("title", "")))


def create_project(title, voice_id, persona=""):
    pid = slugify(title)
    d = PROJECTS / pid
    (d / "clips").mkdir(parents=True)
    _write(d / "project.json", {"title": title, "voice": voice_id, "persona": persona,
                                "created": time.time(), "updated": time.time(),
                                "pacing": dict(DEFAULT_PACING), "order": 100, "pron_lists": ["general"]})
    (d / "script.txt").write_text("")
    return Project(pid)


def audio_duration(path):
    return sf.info(str(path)).duration
