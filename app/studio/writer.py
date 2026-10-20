"""Free script writing with a local Ollama model, section by section.

Runs as one background job at a time. The model is unloaded afterwards (keep_alive 0) so its
memory is back before TTS generation starts.
"""
import re, threading, time

import httpx

from . import store, textprep

OLLAMA = "http://127.0.0.1:11434"
JOB = {"state": "idle"}   # idle | running | done | error
_lock = threading.Lock()


def models():
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=2)
        return [m["name"] for m in r.json().get("models", []) if "embed" not in m["name"]]
    except Exception:
        return None   # Ollama isn't running


def chunks(source, target_words=900):
    """Split notes at headings (or blank lines) into chunks of roughly target_words."""
    blocks = re.split(r"\n(?=[=-]{10,}\n)|\n\s*\n", source)
    out, cur = [], ""
    for b in blocks:
        if cur and len((cur + b).split()) > target_words:
            out.append(cur.strip())
            cur = ""
        cur += b + "\n\n"
    if cur.strip():
        out.append(cur.strip())
    return out


def prompt(settings, chunk, first, last):
    who = settings.get("character", "Shadowheart")
    tone = settings.get("tone", "Firm")
    rules = [
        f"You are {who}, tutoring a law student out loud. Rewrite the study notes below as {who}'s spoken script.",
        f"Tone: {tone.lower()}." + (" Commanding, teasing and in control, demanding answers and rationing praise. "
                                     "Suggestive at most, never explicit." if tone == "Dom" else ""),
    ]
    if settings.get("keep_law", True):
        rules.append("Keep every legal rule, number, period, rule and section number, case name and citation exactly. "
                     "Never invent law. Only the character's own lines are yours to write.")
    if settings.get("lore", True):
        rules.append(f"Add short in-character asides that reference {who}'s world, companions and history.")
    if settings.get("labels", True):
        rules.append('Turn study labels like "Medium." or "Low, one line each" into natural spoken transitions.')
    rules += [
        "Keep each heading line and the ---- or ==== lines around it exactly as given.",
        "Plain text only: no markdown, no bullet symbols, no stage directions.",
        "Open with a short greeting." if first else "Don't greet; continue mid-session.",
        "End with a short sign-off." if last else "Don't sign off; more notes follow.",
    ]
    return "\n".join(rules) + "\n\nNOTES:\n" + chunk + "\n\nSCRIPT:\n"


def start(project, model, settings):
    with _lock:
        if JOB.get("state") == "running":
            raise RuntimeError("A script is already being written.")
        src = project.source.strip()
        if not src:
            raise ValueError("Add your notes first.")
        parts = chunks(src)
        JOB.clear()
        JOB.update(state="running", project=project.id, model=model, done=0, total=len(parts), started=time.time())
    threading.Thread(target=_run, args=(project, model, settings, parts), daemon=True).start()


def _run(project, model, settings, parts):
    out = []
    try:
        for i, chunk in enumerate(parts):
            r = httpx.post(f"{OLLAMA}/api/generate", timeout=900, json={
                "model": model, "prompt": prompt(settings, chunk, i == 0, i == len(parts) - 1), "stream": False,
                "keep_alive": "5m" if i < len(parts) - 1 else 0, "think": False,
                "options": {"temperature": 0.6, "num_ctx": 8192}})
            r.raise_for_status()
            text = re.sub(r"<think>.*?</think>", "", r.json().get("response", ""), flags=re.S).strip()
            out.append(text)
            JOB["done"] = i + 1
        script = "\n\n".join(out).strip() + "\n"
        project.save_script(script)
        JOB.update(state="done", check=textprep.fact_check(project.source, script), finished=time.time())
    except Exception as e:
        JOB.update(state="error", error=f"{type(e).__name__}: {e}")
        try:
            httpx.post(f"{OLLAMA}/api/generate", json={"model": model, "keep_alive": 0}, timeout=5)
        except Exception:
            pass
