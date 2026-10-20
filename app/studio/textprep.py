"""Script text -> TTS-ready sections and paragraphs.

Same rules as projects/shadowheart/clean_script.py, but the pronunciation list comes from
studio/pronunciations.json so it can be edited in the app.
"""
import re

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

# Spelled out letter by letter wherever they appear as a whole word.
ACRONYMS = ["JDR", "ADR", "SPA", "MRs", "MR", "SC", "PNB", "IRAS", "LED", "FEC", "RTC", "MTC", "TRO"]


def words(n):
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000: return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + words(n % 100))
    if n < 1_000_000: return words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + words(n % 1000))
    return words(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + words(n % 1_000_000))


def year(n):
    if 2000 <= n <= 2009: return "two thousand" + ("" if n == 2000 else " " + ONES[n - 2000])
    return words(n // 100) + " " + words(n % 100)


def speak(t, prons):
    """Apply pronunciations (longest first), spell acronyms, numbers to words, drop list labels and quotes."""
    for p in sorted(prons, key=lambda p: -len(p["term"])):
        t = t.replace(p["term"], p["say"])
    acr = r"\b(" + "|".join(sorted(ACRONYMS, key=len, reverse=True)) + r")\b"
    t = re.sub(acr, lambda m: "-".join(m.group().rstrip("s")) + ("s" if m.group().endswith("s") else ""), t)
    t = re.sub(r"^\([a-m]\)\s+", "", t)
    t = re.sub(r"\b(19|20)\d\d\b", lambda m: year(int(m.group())), t)
    t = re.sub(r"\b\d+\b", lambda m: words(int(m.group())), t)
    return t.replace('"', "").strip()


def heading(h, prons):
    h = speak(h, prons)
    h = re.sub(r"\s+-\s+", ". ", h).lower()
    h = re.sub(r"\b(rule|section)\b", lambda m: m.group().capitalize(), h)
    return (h[:1].upper() + h[1:]).rstrip(".") + "."


RULE = re.compile(r"[-=]{10,}")


def parse(script, prons, skip_header_lines=8):
    """Split a script into sections of spoken paragraphs.

    A heading is a line between two rule lines (----- or =====). The first lines of the file are a
    title block when it starts with one (as the Shadowheart scripts do) and aren't spoken.
    """
    lines = script.splitlines()
    has_title_block = len(lines) > 6 and any(RULE.fullmatch(l.strip()) for l in lines[:7])
    skip = skip_header_lines if has_title_block else 0
    sections, cur = [], {"title": "Introduction", "paras": []}
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if i >= skip and RULE.fullmatch(ln) and i + 2 < len(lines) and RULE.fullmatch(lines[i + 2].strip()):
            if cur["paras"]:
                sections.append(cur)
            title = lines[i + 1].strip()
            cur = {"title": title, "paras": [heading(title, prons)]}
            i += 3
            continue
        if i < skip or not ln or RULE.fullmatch(ln):
            i += 1
            continue
        spoken = speak(ln, prons)
        if spoken:
            cur["paras"].append(spoken)
        i += 1
    if cur["paras"]:
        sections.append(cur)
    return sections


def fact_check(source, script):
    """Numbers and citations in the source that the script lost (or added)."""
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
        "headings_source": len(RULE.findall(source)) // 2, "headings_script": len(RULE.findall(script)) // 2,
    }
