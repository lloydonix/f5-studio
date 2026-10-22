"""Optional splitting of long projects into parts, each under a generation-time budget (5 hours by default).

Parts are runs of whole sections. The boundaries are planned once, when splitting is turned on, and stored
(project.json "split.starts": the first section of each part), so they don't move while the speed estimate
changes during generation. Generation runs in order, so parts finish one after another; with auto-export on,
each part's MP3 goes to Downloads as soon as its last paragraph is done.
"""
import hashlib

DEFAULT_HOURS = 5
WORDS_PER_SEC = 2.5      # speaking pace before any audio exists to measure it


def settings(project):
    s = dict(project.meta.get("split") or {})
    s.setdefault("enabled", False)
    s.setdefault("hours", DEFAULT_HOURS)
    s.setdefault("auto_export", True)
    s.setdefault("dismissed", False)     # "keep as one": stop offering for this project
    s.setdefault("starts", [])
    s.setdefault("exported", {})         # part number -> signature of the clips it was exported from
    return s


def _pace(sections):
    done = [p for s in sections for p in s["paras"] if p["dur"]]
    secs = sum(p["dur"] for p in done)
    return sum(len(p["text"].split()) for p in done) / secs if secs > 60 else WORDS_PER_SEC


def section_estimates(sections, ratio):
    """Per section: (audio seconds, generation seconds). Real lengths where generated, estimates elsewhere."""
    pace, out = _pace(sections), []
    for s in sections:
        audio = sum(p["dur"] or len(p["text"].split()) / pace for p in s["paras"])
        out.append((audio, audio * ratio))
    return out


def plan_starts(gen_secs, budget, heading_only=()):
    """First section of each part. A part never ends on a heading-only section (like a bare
    "RULE 39" banner): that heading moves to the start of the next part, with what it introduces."""
    starts, acc = [0], 0.0
    for i, g in enumerate(gen_secs):
        if acc and acc + g > budget:
            j = i
            while j - 1 > starts[-1] and j - 1 < len(heading_only) and heading_only[j - 1]:
                j -= 1
            starts.append(j)
            acc = sum(gen_secs[j:i])
        acc += g
    return starts


def _heading_only(sections):
    """Sections that only introduce what follows: a heading, maybe with a line or two under it."""
    return [sum(len(p["text"].split()) for p in s["paras"]) <= 60 for s in sections]


def _starts(s, n_sections):
    st = sorted({i for i in s["starts"] if 0 < i < n_sections} | {0})
    return st if n_sections else []


def signature(sections, first, last):
    keys = "".join(p["key"] for s in sections[first:last + 1] for p in s["paras"])
    return hashlib.sha1(keys.encode()).hexdigest()[:12]


def ranges(project, sections):
    """[(part number, first section, last section)] for a split project."""
    st = _starts(settings(project), len(sections))
    return [(n + 1, a, (st[n + 1] - 1) if n + 1 < len(st) else len(sections) - 1) for n, a in enumerate(st)]


def summary(project, sections, ratio):
    s = settings(project)
    est = section_estimates(sections, ratio)
    total_gen = sum(g for _, g in est)
    budget = s["hours"] * 3600
    out = {k: s[k] for k in ("enabled", "hours", "auto_export", "dismissed")}
    out.update(total_gen=round(total_gen), total_audio=round(sum(a for a, _ in est)),
               over=total_gen > budget, suggested=len(plan_starts([g for _, g in est], budget, _heading_only(sections))),
               suggest=total_gen > budget and not s["enabled"] and not s["dismissed"], parts=[])
    if s["enabled"]:
        names = {e.get("part"): e for e in project.exports() if e.get("part")}
        for n, a, b in ranges(project, sections):
            paras = [p for x in sections[a:b + 1] for p in x["paras"]]
            done = sum(1 for p in paras if p["dur"])
            complete = bool(paras) and done == len(paras)
            out["parts"].append({
                "n": n, "first": a, "last": b, "first_title": sections[a]["title"], "last_title": sections[b]["title"],
                "done": done, "total": len(paras), "complete": complete,
                "audio": round(sum(x[0] for x in est[a:b + 1])), "gen": round(sum(x[1] for x in est[a:b + 1])),
                "gen_left": round(sum(len(p["text"].split()) / _pace(sections) * ratio for p in paras if not p["dur"])),
                "exported": bool(complete and s["exported"].get(str(n)) == signature(sections, a, b)),
                "file": names.get(n, {}).get("name"),
            })
    return out


def enable(project, sections, ratio, hours=None):
    s = settings(project)
    s["hours"] = hours or s["hours"]
    est = section_estimates(sections, ratio)
    s.update(enabled=True, dismissed=False,
             starts=plan_starts([g for _, g in est], s["hours"] * 3600, _heading_only(sections)))
    project.save_meta(split=s)
    return s


def update(project, change, sections, ratio):
    s = settings(project)
    for k in ("auto_export", "dismissed"):
        if k in change:
            s[k] = bool(change[k])
    if change.get("enabled") is False:
        s["enabled"] = False
    project.save_meta(split=s)
    if change.get("enabled") or ("hours" in change and s["enabled"]):
        return enable(project, sections, ratio, float(change.get("hours") or s["hours"]))
    if "hours" in change:
        s["hours"] = float(change["hours"])
        project.save_meta(split=s)
    return s


def mark_exported(project, n, sig):
    s = settings(project)
    s["exported"][str(n)] = sig
    project.save_meta(split=s)


def after_clip(project, si):
    """Called after each generated paragraph: export its part if that finished it (auto-export on)."""
    s = settings(project)
    if not (s["enabled"] and s["auto_export"]):
        return None
    from . import export
    sections = project.sections()
    for n, a, b in ranges(project, sections):
        if a <= si <= b:
            if all(p["dur"] for x in sections[a:b + 1] for p in x["paras"]) and \
                    s["exported"].get(str(n)) != signature(sections, a, b):
                return export.merge(project, part=n)
            return None
    return None
