"""Script text -> TTS-ready sections and paragraphs.

Pronunciations and acronyms come from the pronunciation lists the project uses (store.merged_prons).
"""
import re

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

def words(n):
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000: return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + words(n % 100))
    if n < 1_000_000: return words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + words(n % 1000))
    return words(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + words(n % 1_000_000))


def year(n):
    if 2000 <= n <= 2009: return "two thousand" + ("" if n == 2000 else " " + ONES[n - 2000])
    return words(n // 100) + " " + words(n % 100)


def speak(t, prons, acronyms=()):
    """Apply pronunciations (longest first), spell acronyms, numbers to words, drop list labels and quotes."""
    for p in sorted(prons, key=lambda p: -len(p["term"])):
        t = t.replace(p["term"], p["say"])
    if acronyms:
        acr = r"\b(" + "|".join(re.escape(a) for a in sorted(acronyms, key=len, reverse=True)) + r")\b"
        t = re.sub(acr, lambda m: "-".join(m.group().rstrip("s")) + ("s" if m.group().endswith("s") else ""), t)
    t = re.sub(r"^\([a-m]\)\s+", "", t)
    t = re.sub(r"\b(19|20)\d\d\b", lambda m: year(int(m.group())), t)
    t = re.sub(r"\b\d+\b", lambda m: words(int(m.group())), t)
    return t.replace('"', "").strip()


def heading(h, prons, acronyms=()):
    h = speak(h, prons, acronyms)
    h = re.sub(r"\s+-\s+", ". ", h).lower()
    h = re.sub(r"\b(rule|section)\b", lambda m: m.group().capitalize(), h)
    return (h[:1].upper() + h[1:]).rstrip(".") + "."


RULE = re.compile(r"[-=]{10,}")
MD_HEADING = re.compile(r"#{1,4}\s+(\S.*)")


def parse(script, prons, acronyms=(), skip_header_lines=8):
    """Split a script into sections of spoken paragraphs. Each non-empty line is one paragraph.

    A heading is a Markdown heading line (# Chapter One) or a line between two rule lines
    (----- or =====). When a file opens with a ruled title block, its first lines aren't spoken.
    """
    lines = script.splitlines()
    has_title_block = len(lines) > 6 and any(RULE.fullmatch(l.strip()) for l in lines[:7])
    skip = skip_header_lines if has_title_block else 0
    sections, cur = [], {"title": "Opening", "paras": []}
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if i >= skip and RULE.fullmatch(ln) and i + 2 < len(lines) and RULE.fullmatch(lines[i + 2].strip()):
            if cur["paras"]:
                sections.append(cur)
            title = lines[i + 1].strip()
            cur = {"title": title, "paras": [heading(title, prons, acronyms)]}
            i += 3
            continue
        md = i >= skip and MD_HEADING.fullmatch(ln)
        if md:
            if cur["paras"]:
                sections.append(cur)
            title = md.group(1).strip().strip("#").strip()
            cur = {"title": title, "paras": [heading(title, prons, acronyms)]}
            i += 1
            continue
        if i < skip or not ln or RULE.fullmatch(ln):
            i += 1
            continue
        spoken = speak(ln, prons, acronyms)
        if spoken:
            cur["paras"].append(spoken)
        i += 1
    if cur["paras"]:
        sections.append(cur)
    return sections


def fact_check(source, script):
    """Numbers, case citations and headings in the original text that the script lost."""
    def nums(t):
        return re.findall(r"\d+(?:\([a-z]\))?", t)
    def cites(t):
        return re.findall(r"G\.R\. No\. \d+|A\.M\. No\. [\w-]+|\b[A-Z][a-zA-Z-]+ v\. [A-Z][\w-]+", t)
    from collections import Counter
    ns, nt = Counter(nums(source)), Counter(nums(script))
    cs, ct = Counter(cites(source)), Counter(cites(script))
    return {
        "numbers": sum(ns.values()), "numbers_missing": sorted((ns - nt).elements()),
        "citations": sum(cs.values()), "citations_missing": sorted((cs - ct).elements()),
        "headings_source": _headings(source), "headings_script": _headings(script),
    }


def _headings(t):
    return len(RULE.findall(t)) // 2 + len(re.findall(r"(?m)^\s*#{1,4}\s+\S", t))
