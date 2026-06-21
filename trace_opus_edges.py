#!/usr/bin/env python3
"""Trace why Opus linked node A -> node B: locate both in the .tex and inspect
the dependent node's body/proof for the cause (explicit \\ref, name mention, or
purely semantic)."""
import json, re, pathlib, sys

PID = sys.argv[1] if len(sys.argv) > 1 else "011"
TEX = pathlib.Path(f"/Users/yaronot/Datasets/Authomathics_data/alignment/papers/paper{PID}/source/paper{PID}.tex").read_text(encoding="utf-8", errors="replace")
d = json.load(open(f"portal/data/tier2/paper{PID}.json"))
nodes = d["nodes"]
id2 = {n["id"]: n for n in nodes}

REF = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|vref)\{([^}]+)\}")
LABEL = re.compile(r"\\label\{([^}]+)\}")


def loc(node):
    stmt = re.sub(r"\s+", " ", node["statement"]).strip()
    words = stmt.split()[:6]
    if not words:
        return None
    pat = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pat, TEX)
    return m.start() if m else None


def label_near(pos, back=300, fwd=400):
    if pos is None:
        return None
    seg = TEX[max(0, pos - back):pos + fwd]
    m = LABEL.search(seg)
    return m.group(1) if m else None


def analyze(src, tgt):
    sp, tp = loc(src), loc(tgt)
    slabel = label_near(sp)
    print("=" * 72)
    print(f"PREREQ  {src['type']}: {src['name'][:50]!r}")
    print(f"  --used by-->  {tgt['type']}: {tgt['name'][:50]!r}")
    if tp is None:
        print("  (could not locate dependent node in tex)")
        return
    # dependent body window: statement + following text (likely its proof)
    win = TEX[tp:tp + 1600]
    refs = REF.findall(win)
    cause = []
    if slabel and slabel in win:
        cause.append(f"EXPLICIT \\ref to prereq label '{slabel}'")
    # name-word overlap
    namewords = [w for w in re.sub(r"[^a-zA-Z ]", " ", src["name"]).split() if len(w) > 4][:3]
    hits = [w for w in namewords if re.search(r"\b" + re.escape(w) + r"\b", win, re.I)]
    if hits:
        cause.append(f"TEXTUAL name mention {hits}")
    if not cause:
        cause.append("NO ref/name in dependent body -> SEMANTIC (Opus inferred it)")
    print(f"  prereq label: {slabel!r} | refs in dependent body: {refs[:6]}")
    print(f"  CAUSE: {' + '.join(cause)}")
    # show the snippet of evidence
    if slabel and slabel in win:
        i = win.find(slabel)
        print(f"  evidence: ...{win[max(0,i-60):i+30].strip()}...")
    elif hits:
        i = win.lower().find(hits[0].lower())
        print(f"  evidence: ...{win[max(0,i-50):i+60].strip()}...")


def classify(src, tgt):
    sp, tp = loc(src), loc(tgt)
    slabel = label_near(sp)
    if tp is None:
        return "UNLOCATED", None
    win = TEX[tp:tp + 1600]
    if slabel and slabel in win:
        return "EXPLICIT_REF", f"\\ref{{{slabel}}}"
    namewords = [w for w in re.sub(r"[^a-zA-Z ]", " ", src["name"]).split() if len(w) > 4][:3]
    hits = [w for w in namewords if re.search(r"\b" + re.escape(w) + r"\b", win, re.I)]
    if hits:
        return "TEXTUAL_NAME", str(hits)
    return "SEMANTIC", None


uses = [(id2[e["source"]], id2[e["target"]]) for e in d["edges"] if e.get("type") == "uses"]
from collections import Counter, defaultdict
tally = Counter()
examples = defaultdict(list)
for src, tgt in uses:
    cat, ev = classify(src, tgt)
    tally[cat] += 1
    if len(examples[cat]) < 3:
        examples[cat].append((src["type"], src["name"][:30], tgt["type"], tgt["name"][:30], ev))
print(f"paper{PID}: {len(uses)} 'uses' edges — cause breakdown:")
for cat, c in tally.most_common():
    print(f"  {cat:14s}: {c}")
print()
for cat in ("TEXTUAL_NAME", "EXPLICIT_REF", "SEMANTIC"):
    if examples[cat]:
        print(f"--- {cat} examples ---")
        for st, sn, tt, tn, ev in examples[cat]:
            print(f"  {st}:{sn!r} -> {tt}:{tn!r}  [{ev}]")
